-- Cyber City Oedo 808 - dialogue VRAM clobber profiler
-- Mesen 2.2.1 / PC Engine CD
--
-- READ ONLY. Measures which VRAM bytes actually change between the start of a
-- Mission 0 dialogue load and the start of the stock $22E8 full exploration
-- VRAM restore. The stock exploration image occupies VDC word addresses
-- $0900-$7FFF (0xEE00 bytes). Dialogue is known to place portraits at $4000,
-- glyph patterns at $6D00, and the dialogue BAT near $7900, all inside that
-- exploration image.
--
-- If the changed ranges are much smaller than 0xEE00 bytes, a future build can
-- test restoring only dialogue-clobbered scene ranges from a RAM cache instead
-- of retransferring the complete scene image from CD.
--
-- Persistent log: cyber_oedo_dialogue_vram_clobber.log

local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory
local VRAM = emu.memType.pceVideoRam

local frame = 0
local active = false
local dirty = {}
local dirtyCount = 0
local writeCount = 0
local changedWriteCount = 0
local session = 0
local logFile = nil

local function r8(address, memType)
  return emu.read(address, memType or MEM)
end

local function openLog()
  if type(io) ~= "table" or type(io.open) ~= "function" then return end
  local base = emu.getScriptDataFolder()
  if not base or base == "" then return end
  logFile = io.open(base .. "/cyber_oedo_dialogue_vram_clobber.log", "a")
  if logFile then
    logFile:write("\n=== NEW VRAM CLOBBER SESSION ===\n")
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

local function currentCdLba()
  return (r8(0x20FC) << 16) | (r8(0x20FD) << 8) | r8(0x20FE)
end

local function resetDirty()
  dirty = {}
  dirtyCount = 0
  writeCount = 0
  changedWriteCount = 0
end

local function summarize()
  local addresses = {}
  for address,_ in pairs(dirty) do
    addresses[#addresses+1] = address
  end
  table.sort(addresses)

  log(string.format(
    "[VRAM_DIRTY_SUMMARY %d] frame=%d unique_changed_bytes=%d " ..
    "all_writes=%d changed_writes=%d",
    session, frame, dirtyCount, writeCount, changedWriteCount
  ))

  if #addresses == 0 then return end
  local first = addresses[1]
  local last = first
  local rangeCount = 0

  local function emitRange(a, b)
    rangeCount = rangeCount + 1
    if rangeCount <= 128 then
      log(string.format(
        "[VRAM_DIRTY_RANGE %03d] byte=$%04X-$%04X bytes=%d " ..
        "vdc_word~=$%04X-$%04X",
        rangeCount, a, b, b-a+1, a >> 1, b >> 1
      ))
    end
  end

  for index=2,#addresses do
    local address = addresses[index]
    if address == last + 1 then
      last = address
    else
      emitRange(first, last)
      first = address
      last = address
    end
  end
  emitRange(first, last)
  log(string.format("[VRAM_DIRTY_RANGES_TOTAL] %d", rangeCount))
end

local function onCdRead()
  local lba = currentCdLba()

  -- The Mission 0 dialogue module is the first known dialogue-side optical
  -- request. Starting here captures portrait and renderer initialization that
  -- occurs before the first parser execution.
  if lba == 0x1425 and not active then
    session = session + 1
    resetDirty()
    active = true
    log(string.format(
      "[VRAM_TRACK_START %d] frame=%d lba=$%04X",
      session, frame, lba
    ))
    return
  end

  -- $22E8 is the stock 0xEE00-byte scene-graphics restore itself. Stop before
  -- that transfer so it does not contaminate the dialogue dirty map.
  if lba == 0x22E8 and active then
    active = false
    log(string.format(
      "[VRAM_TRACK_STOP %d] frame=%d before_scene_restore_lba=$%04X",
      session, frame, lba
    ))
    summarize()
  end
end

local function onVramWrite(address, value)
  if not active then return end
  writeCount = writeCount + 1
  local old = r8(address, VRAM)
  if old == value then return end
  changedWriteCount = changedWriteCount + 1
  if not dirty[address] then
    dirty[address] = true
    dirtyCount = dirtyCount + 1
  end
end

openLog()
log("Cyber City Oedo 808 dialogue VRAM clobber profiler armed. Read-only: YES")

emu.addMemoryCallback(onCdRead, emu.callbackType.exec, 0xE009, 0xE009, CPU, MEM)
emu.addMemoryCallback(
  onVramWrite, emu.callbackType.write,
  0, 0xFFFF, CPU, VRAM
)

emu.addEventCallback(function()
  frame = frame + 1
end, emu.eventType.endFrame)

emu.addEventCallback(function()
  if active then
    log("[SCRIPT_END_WITH_ACTIVE_TRACK]")
    summarize()
  end
  if logFile then
    logFile:flush()
    logFile:close()
    logFile = nil
  end
end, emu.eventType.scriptEnded)
