-- Cyber City Oedo 808 - Mission 0 dialogue residency profiler
-- Mesen 2.2.1 / PC Engine CD
--
-- READ ONLY.  Proves or falsifies the proposed bank-$85 resident-dialogue
-- fast path.  The loaded Mission 0 layout is:
--
--   physical $A000-$AF50  logical $8000-$8F50 module body
--   physical $AF51-$AFFF  logical $8F51-$8FFF runtime/BSS
--   physical $B000-$BFFF  logical $9000-$9FFF speaker-local block
--
-- The module body is self-modifying only at logical $8617/$8618.  Checksums
-- deliberately exclude physical $A617/$A618.  A cache fast path is not safe
-- unless the immutable checksum survives dialogue -> exploration -> next
-- module-loader entry.
--
-- Persistent log: cyber_oedo_dialogue_residency.log

local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory
local CDRAM = emu.memType.pceCdromRam

local frame = 0
local logFile = nil

local MODULE_PHYS_START = 0xA000
local MODULE_LENGTH = 0x0F51
local MODULE_PHYS_END = MODULE_PHYS_START + MODULE_LENGTH - 1
local MUTABLE_A = 0xA617
local MUTABLE_B = 0xA618
local SPEAKER_PHYS_START = 0xB000
local SPEAKER_PHYS_END = 0xBFFF

local baselineModule = nil
local baselineSpeaker = nil
local moduleLoads = 0
local immutableWritesAfterLoad = 0
local mutableWritesAfterLoad = 0
local speakerWritesAfterLoad = 0
local adTransCalls = 0
local lastAdTransFrame = -1
local lifecycleBaselineModule = nil
local lifecycleBaselineSpeaker = nil

local function r8(address, memType)
  return emu.read(address, memType or MEM)
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

local function openLog()
  if type(io) ~= "table" or type(io.open) ~= "function" then return end
  local base = emu.getScriptDataFolder()
  if not base or base == "" then return end
  logFile = io.open(base .. "/cyber_oedo_dialogue_residency.log", "a")
  if logFile then
    logFile:write("\n=== NEW DIALOGUE RESIDENCY SESSION ===\n")
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

-- Adler-32 is used only as a compact equality fingerprint between lifecycle
-- points. This is not a cryptographic source-authentication mechanism.
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

local function logicalState()
  return string.format(
    "sig=%02X/%02X selfmod=%02X%02X req=$%02X cache=$%02X " ..
    "audio=$%02X voice=$%02X flag420B=$%02X",
    r8(0x8000), r8(0x8003),
    r8(0x8618), r8(0x8617),
    r8(0x8FDD), r8(0x8FDE),
    r8(0x37F0), r8(0x37F1), r8(0x420B)
  )
end

local function isMission0TextOverlay()
  local m = mprs()
  return m[2] == 0x80 and m[3] == 0x81
end

local function onModuleProbe()
  if not isMission0TextOverlay() then return end
  local currentModule = moduleChecksum()
  local currentSpeaker = speakerChecksum()
  log(string.format(
    "[MODULE_PROBE] frame=%d module_adler=$%08X speaker_adler=$%08X " ..
    "module_baseline=%s speaker_baseline=%s immutable_writes=%d " ..
    "mutable_writes=%d speaker_writes=%d %s %s",
    frame, currentModule, currentSpeaker,
    baselineModule and string.format("$%08X", baselineModule) or "none",
    baselineSpeaker and string.format("$%08X", baselineSpeaker) or "none",
    immutableWritesAfterLoad, mutableWritesAfterLoad, speakerWritesAfterLoad,
    logicalState(), mprString()
  ))
  if baselineModule then
    log(string.format(
      "[MODULE_RESIDENCY_RESULT] immutable_match=%s speaker_match=%s",
      currentModule == baselineModule and "yes" or "no",
      baselineSpeaker and currentSpeaker == baselineSpeaker and "yes" or "no"
    ))
  end
end

local function onModuleLoadReturn()
  if not isMission0TextOverlay() then return end
  moduleLoads = moduleLoads + 1
  baselineModule = moduleChecksum()
  immutableWritesAfterLoad = 0
  mutableWritesAfterLoad = 0
  -- Do not update speaker baseline here: module reload deliberately ends at
  -- $8F50 and preserves both BSS and $9000-$9FFF.
  log(string.format(
    "[MODULE_LOAD_RETURN %d] frame=%d module_adler=$%08X %s %s",
    moduleLoads, frame, baselineModule, logicalState(), mprString()
  ))
end

local function onCommand1()
  if not isMission0TextOverlay() then return end
  log(string.format(
    "[COMMAND1] frame=%d requested=$%02X cached=$%02X ad_trans_count=%d %s",
    frame, r8(0x8FDD), r8(0x8FDE), adTransCalls, logicalState()
  ))
end

local function onAfterLocalBlockDecision()
  if not isMission0TextOverlay() then return end
  baselineSpeaker = speakerChecksum()
  speakerWritesAfterLoad = 0
  log(string.format(
    "[LOCAL_BLOCK_READY] frame=%d selector=$%02X speaker_adler=$%08X %s",
    frame, r8(0x8FDE), baselineSpeaker, logicalState()
  ))
end

local function onCommand2()
  if not isMission0TextOverlay() then return end
  log(string.format("[COMMAND2_FADE] frame=%d %s", frame, logicalState()))
end

local function logLifecycle(tag)
  local module = moduleChecksum()
  local speaker = speakerChecksum()
  local moduleMatch = lifecycleBaselineModule and module == lifecycleBaselineModule
  local speakerMatch = lifecycleBaselineSpeaker and speaker == lifecycleBaselineSpeaker
  log(string.format(
    "[%s] frame=%d module_adler=$%08X speaker_adler=$%08X " ..
    "module_match=%s speaker_match=%s immutable_writes=%d mutable_writes=%d " ..
    "speaker_writes=%d %s %s",
    tag, frame, module, speaker,
    lifecycleBaselineModule and (moduleMatch and "yes" or "no") or "n/a",
    lifecycleBaselineSpeaker and (speakerMatch and "yes" or "no") or "n/a",
    immutableWritesAfterLoad, mutableWritesAfterLoad, speakerWritesAfterLoad,
    logicalState(), mprString()
  ))
end

local function onCommand5()
  if not isMission0TextOverlay() then return end
  lifecycleBaselineModule = moduleChecksum()
  lifecycleBaselineSpeaker = speakerChecksum()
  logLifecycle("COMMAND5_TEARDOWN")
end

local function onExplorationEntry()
  logLifecycle("EXPLORATION_ENTRY")
end

local function onInteractiveLoop()
  logLifecycle("EXPLORATION_INTERACTIVE")
end

local function onAdTrans()
  adTransCalls = adTransCalls + 1
  lastAdTransFrame = frame
  log(string.format(
    "[AD_TRANS %d] frame=%d source=%02X:%02X:%02X blocks=$%02X " ..
    "set_addr=$%02X caller_return=$%04X %s %s",
    adTransCalls, frame,
    r8(0x20FC), r8(0x20FD), r8(0x20FE), r8(0x20F8), r8(0x20FF),
    stackReturnTarget(), logicalState(), mprString()
  ))
end

local function onModuleWrite(address)
  if address == MUTABLE_A or address == MUTABLE_B then
    mutableWritesAfterLoad = mutableWritesAfterLoad + 1
  else
    immutableWritesAfterLoad = immutableWritesAfterLoad + 1
    if immutableWritesAfterLoad <= 32 then
      log(string.format(
        "[IMMUTABLE_MODULE_WRITE %d] frame=%d phys=$%04X value=$%02X PC=$%04X %s",
        immutableWritesAfterLoad, frame, address, r8(address, CDRAM),
        cpu().pc or 0, mprString()
      ))
    end
  end
end

local function onSpeakerWrite(address)
  speakerWritesAfterLoad = speakerWritesAfterLoad + 1
  if speakerWritesAfterLoad <= 16 then
    log(string.format(
      "[SPEAKER_BLOCK_WRITE %d] frame=%d phys=$%04X value=$%02X PC=$%04X",
      speakerWritesAfterLoad, frame, address, r8(address, CDRAM), cpu().pc or 0
    ))
  end
end

openLog()
log("Cyber City Oedo 808 dialogue residency profiler armed. Read-only: YES")

emu.addMemoryCallback(onModuleProbe, emu.callbackType.exec, 0x48A6, 0x48A6, CPU, MEM)
emu.addMemoryCallback(onModuleLoadReturn, emu.callbackType.exec, 0x48CD, 0x48CD, CPU, MEM)
emu.addMemoryCallback(onCommand1, emu.callbackType.exec, 0x802D, 0x802D, CPU, MEM)
emu.addMemoryCallback(onAfterLocalBlockDecision, emu.callbackType.exec, 0x8053, 0x8053, CPU, MEM)
emu.addMemoryCallback(onCommand2, emu.callbackType.exec, 0x80E7, 0x80E7, CPU, MEM)
emu.addMemoryCallback(onCommand5, emu.callbackType.exec, 0x813E, 0x813E, CPU, MEM)
emu.addMemoryCallback(onExplorationEntry, emu.callbackType.exec, 0x4000, 0x4000, CPU, MEM)
emu.addMemoryCallback(onInteractiveLoop, emu.callbackType.exec, 0x4012, 0x4012, CPU, MEM)
emu.addMemoryCallback(onAdTrans, emu.callbackType.exec, 0xE033, 0xE033, CPU, MEM)

emu.addMemoryCallback(
  onModuleWrite, emu.callbackType.write,
  MODULE_PHYS_START, MODULE_PHYS_END, CPU, CDRAM
)
emu.addMemoryCallback(
  onSpeakerWrite, emu.callbackType.write,
  SPEAKER_PHYS_START, SPEAKER_PHYS_END, CPU, CDRAM
)

emu.addEventCallback(function()
  frame = frame + 1
  if frame % 600 == 0 then
    log(string.format(
      "[HEARTBEAT] frame=%d module=$%08X speaker=$%08X " ..
      "immutable_writes=%d mutable_writes=%d speaker_writes=%d ad_trans=%d %s",
      frame, moduleChecksum(), speakerChecksum(),
      immutableWritesAfterLoad, mutableWritesAfterLoad, speakerWritesAfterLoad,
      adTransCalls, mprString()
    ))
  end
end, emu.eventType.endFrame)

emu.addEventCallback(function()
  log(string.format(
    "[SUMMARY] frames=%d module_loads=%d immutable_writes=%d mutable_writes=%d " ..
    "speaker_writes=%d ad_trans=%d last_ad_trans_frame=%d",
    frame, moduleLoads, immutableWritesAfterLoad, mutableWritesAfterLoad,
    speakerWritesAfterLoad, adTransCalls, lastAdTransFrame
  ))
  if logFile then
    logFile:flush()
    logFile:close()
    logFile = nil
  end
end, emu.eventType.scriptEnded)
