-- Cyber City Oedo 808 - same-room lifetime / re-entry profiler
-- Mesen 2.2.1 / PC Engine CD
--
-- READ ONLY.  Designed to settle several load-time gates in one short capture:
--   * whether the exploration $22DE -> $9000 load maps MPR4 to physical page $85;
--   * whether page-$85 module/speaker halves change across that read;
--   * which scene-entry/object/collision/loader landmarks execute on return;
--   * MPR state at exploration entry and first interactive-loop re-entry.
--
-- Persistent log: cyber_oedo_same_room_lifetime.log

local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory
local CDRAM = emu.memType.pceCdromRam

local frame = 0
local logFile = nil
local readOrdinal = 0
local pending22DE = {}
local registeredReturns = {}
local interactiveArmed = false

local MODULE_PHYS_START = 0xA000
local MODULE_PHYS_END = 0xAF50
local MUTABLE_A = 0xA617
local MUTABLE_B = 0xA618
local SPEAKER_PHYS_START = 0xB000
local SPEAKER_PHYS_END = 0xBFFF

local function r8(address, memType)
  return emu.read(address, memType or MEM)
end

local function r16(address)
  return emu.read16(address, MEM, false)
end

local function cpu()
  return emu.getCpuState(CPU)
end

local function mprs()
  local state = emu.getState()
  local result = {}
  for i=0,7 do
    result[i] = state["memoryManager.mpr[" .. i .. "]"] or 0
  end
  return result
end

local function mprString(values)
  values = values or mprs()
  local out = {}
  for i=0,7 do
    out[#out+1] = string.format("MPR%d=$%02X", i, values[i])
  end
  return table.concat(out, " ")
end

local function stackReturnTarget()
  local state = cpu()
  local sp = state.sp or 0
  local lo = r8(0x2100 + ((sp + 1) & 0xFF))
  local hi = r8(0x2100 + ((sp + 2) & 0xFF))
  return ((((hi << 8) | lo) + 1) & 0xFFFF)
end

local function adlerRange(first, last, skipA, skipB)
  local s1 = 1
  local s2 = 0
  for address=first,last do
    if address ~= skipA and address ~= skipB then
      local value = r8(address, CDRAM)
      s1 = (s1 + value) % 65521
      s2 = (s2 + s1) % 65521
    end
  end
  return ((s2 << 16) | s1) & 0xFFFFFFFF
end

local function moduleChecksum()
  return adlerRange(MODULE_PHYS_START, MODULE_PHYS_END, MUTABLE_A, MUTABLE_B)
end

local function speakerChecksum()
  return adlerRange(SPEAKER_PHYS_START, SPEAKER_PHYS_END, -1, -1)
end

local function sceneState()
  return string.format(
    "scene=$%02X entry=$%02X posmode=$%02X exit=$%02X",
    r8(0x3700), r8(0x3701), r8(0x3702), r8(0x2649)
  )
end

local function openLog()
  if type(io) ~= "table" or type(io.open) ~= "function" then return end
  local base = emu.getScriptDataFolder()
  if not base or base == "" then return end
  logFile = io.open(base .. "/cyber_oedo_same_room_lifetime.log", "a")
  if logFile then
    logFile:write("\n=== NEW SAME ROOM LIFETIME SESSION ===\n")
    logFile:flush()
  end
end

local function log(line)
  print(line)
  if logFile then
    logFile:write(line, "\n")
    logFile:flush()
  end
end

local function logLandmark(name)
  log(string.format(
    "[%s] frame=%d module=$%08X speaker=$%08X %s %s",
    name, frame, moduleChecksum(), speakerChecksum(), sceneState(), mprString()
  ))
end

local function ensureReturnCallback(target)
  if registeredReturns[target] then return end
  registeredReturns[target] = true
  emu.addMemoryCallback(
    function()
      local queue = pending22DE[target]
      if not queue or #queue == 0 then return end
      local item = table.remove(queue, 1)
      local m = mprs()
      local moduleAfter = moduleChecksum()
      local speakerAfter = speakerChecksum()
      log(string.format(
        "[SCENE_LOCAL_B_RETURN %03d] frame=%d elapsed_frames=%d " ..
        "MPR4=$%02X MPR5=$%02X module_before=$%08X module_after=$%08X " ..
        "module_changed=%s speaker_before=$%08X speaker_after=$%08X " ..
        "speaker_changed=%s same_page85_mpr4=%s %s %s",
        item.ordinal, frame, frame - item.startFrame,
        m[4], m[5], item.moduleBefore, moduleAfter,
        moduleAfter ~= item.moduleBefore and "yes" or "no",
        item.speakerBefore, speakerAfter,
        speakerAfter ~= item.speakerBefore and "yes" or "no",
        m[4] == 0x85 and "yes" or "no",
        sceneState(), mprString(m)
      ))
      interactiveArmed = true
    end,
    emu.callbackType.exec,
    target, target, CPU, MEM
  )
end

local function onCdRead()
  local lba = (r8(0x20FC) << 16) | (r8(0x20FD) << 8) | r8(0x20FE)
  local destination = r16(0x20FA)
  if lba ~= 0x22DE or destination ~= 0x9000 then return end

  readOrdinal = readOrdinal + 1
  local target = stackReturnTarget()
  local m = mprs()
  local item = {
    ordinal=readOrdinal,
    startFrame=frame,
    returnTarget=target,
    moduleBefore=moduleChecksum(),
    speakerBefore=speakerChecksum(),
  }
  if not pending22DE[target] then pending22DE[target] = {} end
  table.insert(pending22DE[target], item)
  ensureReturnCallback(target)

  log(string.format(
    "[SCENE_LOCAL_B_START %03d] frame=%d sector=$%06X dest=$%04X len=$%04X " ..
    "type=$%02X caller_return=$%04X MPR4=$%02X MPR5=$%02X " ..
    "module_before=$%08X speaker_before=$%08X same_page85_mpr4=%s %s %s",
    readOrdinal, frame, lba, destination, r16(0x20F8), r8(0x20FF), target,
    m[4], m[5], item.moduleBefore, item.speakerBefore,
    m[4] == 0x85 and "yes" or "no", sceneState(), mprString(m)
  ))
end

openLog()
log("Cyber City Oedo 808 same-room lifetime profiler armed. Read-only: YES")

emu.addMemoryCallback(onCdRead, emu.callbackType.exec, 0xE009, 0xE009, CPU, MEM)

local landmarks = {
  {name="EXPLORATION_ENTRY", address=0x4000},
  {name="EXPLORATION_INTERACTIVE", address=0x4012},
  {name="SCENE_ORCHESTRATION", address=0x40E9},
  {name="SCENE_ENTRY_SELECTION", address=0x419E},
  {name="LOCAL_SCENE_LOADER", address=0x423B},
  {name="VRAM_SCENE_LOADER", address=0x4262},
  {name="COLLISION_RECT_RESET", address=0x470C},
  {name="OBJECT_SOURCE_INIT", address=0x5519},
}

local landmarkCounts = {}
for _, item in ipairs(landmarks) do
  emu.addMemoryCallback(
    function()
      if item.name == "EXPLORATION_INTERACTIVE" then
        if not interactiveArmed then return end
        interactiveArmed = false
      end
      landmarkCounts[item.name] = (landmarkCounts[item.name] or 0) + 1
      logLandmark(item.name .. "_" .. landmarkCounts[item.name])
    end,
    emu.callbackType.exec,
    item.address, item.address, CPU, MEM
  )
end

emu.addEventCallback(function()
  frame = frame + 1
end, emu.eventType.endFrame)

emu.addEventCallback(function()
  log("[SUMMARY] frames=" .. frame .. " scene_local_b_reads=" .. readOrdinal)
  for _, item in ipairs(landmarks) do
    log(string.format("%s=%d", item.name, landmarkCounts[item.name] or 0))
  end
  if logFile then
    logFile:flush()
    logFile:close()
    logFile = nil
  end
end, emu.eventType.scriptEnded)
