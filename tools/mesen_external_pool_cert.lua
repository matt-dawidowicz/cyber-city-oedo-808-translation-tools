-- Cyber City Oedo 808 - external English-pool certification trace
-- MesenCE 2.2.1 / PC Engine CD
--
-- READ ONLY.  This trace is intentionally narrow: it records the release gate
-- for 27 28 7B redirected dialogue without changing CPU/RAM/disc state.
--
-- Required successful order:
--   parser sees $7B redirect
--   -> CD_READ touches the reserved English-pool LBA range
--   -> parser later consumes $7D $45 native-English segment bytes
--   -> stock cell renderer executes
--   -> parser continues into an ordinary low-byte control / terminator.
--
-- The HuC6280 direct page lives at physical $2000-$20FF.  Reading $007F from
-- Mesen's pceMemory space does NOT read the parser's ($7F) pointer.

local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory
local DP = 0x2000

local TRACK2_START_LBA = 3590
local POOL_FIRST_RELATIVE = 0xA059
local POOL_LAST_RELATIVE = 0xA0C0
local POOL_FIRST_LBA = TRACK2_START_LBA + POOL_FIRST_RELATIVE
local POOL_LAST_LBA = TRACK2_START_LBA + POOL_LAST_RELATIVE

local parsers = {
  {name="M0_A_or_M8", pc=0x94A7},
  {name="M0_B",       pc=0x9543},
  {name="M1",         pc=0x95AA},
  {name="M2",         pc=0x95AE},
  {name="M3",         pc=0x9580},
  {name="M4",         pc=0x950E},
  {name="M5",         pc=0x9581},
  {name="M6",         pc=0x9526},
  {name="M7",         pc=0x94A8},
}

local frame = 0
local parserHits = 0
local redirectHits = 0
local nativeHits = 0
local poolReads = 0
local rendererAfterRedirect = 0
local sawRedirect = false
local sawPoolRead = false
local sawNative = false
local sawRenderer = false
local sawCleanReturn = false
local logFile = nil

local function r8(address)
  return emu.read(address, MEM)
end

local function r16(address)
  local lo = r8(address)
  local hi = r8((address + 1) & 0xFFFF)
  return lo | (hi << 8)
end

local function dp8(address)
  return r8(DP + (address & 0xFF))
end

local function dp16(address)
  local lo = dp8(address)
  local hi = dp8(address + 1)
  return lo | (hi << 8)
end

local function cpu()
  return emu.getCpuState(CPU)
end

local function mpr_string()
  local state = emu.getState()
  local parts = {}
  for i=0,7 do
    parts[#parts+1] = string.format(
      "MPR%d=$%02X", i, state["memoryManager.mpr[" .. i .. "]"] or 0
    )
  end
  return table.concat(parts, " ")
end

local function open_log()
  if type(io) ~= "table" or type(io.open) ~= "function" then return end
  local base = emu.getScriptDataFolder()
  if not base or base == "" then return end
  logFile = io.open(base .. "/cyber_oedo_external_pool_cert.log", "a")
end

local function log(line)
  print(line)
  if logFile then
    logFile:write(line, "\n")
    logFile:flush()
  end
end

local function bytes_at(pointer, count)
  local parts = {}
  for i=0,count-1 do
    parts[#parts+1] = string.format("%02X", r8((pointer + i) & 0xFFFF))
  end
  return table.concat(parts, " ")
end

local function parser_hit(name)
  parserHits = parserHits + 1
  local ptr = dp16(0x7F)
  local b0 = r8(ptr)
  local b1 = r8((ptr + 1) & 0xFFFF)

  if b0 == 0x7B then
    redirectHits = redirectHits + 1
    sawRedirect = true
    log(string.format(
      "[REDIRECT] frame=%d parser=%s ptr=$%04X bytes=%s %s",
      frame, name, ptr, bytes_at(ptr, 8), mpr_string()
    ))
    return
  end

  if sawRedirect and b0 == 0x7D and b1 == 0x45 then
    nativeHits = nativeHits + 1
    sawNative = true
    log(string.format(
      "[NATIVE] frame=%d parser=%s ptr=$%04X bytes=%s %s",
      frame, name, ptr, bytes_at(ptr, 8), mpr_string()
    ))
    return
  end

  if sawRenderer and b0 < 0x80 then
    sawCleanReturn = true
    log(string.format(
      "[CONTROL_RETURN] frame=%d parser=%s ptr=$%04X next=$%02X %s",
      frame, name, ptr, b0, mpr_string()
    ))
  end
end

local function cd_read_hit()
  -- Game/System Card CD_READ convention uses $FC/$FD/$FE as
  -- [high, low, middle] LBA bytes.
  local high = dp8(0xFC)
  local low = dp8(0xFD)
  local middle = dp8(0xFE)
  local lba = (high << 16) | (middle << 8) | low
  if lba >= POOL_FIRST_LBA and lba <= POOL_LAST_LBA then
    poolReads = poolReads + 1
    sawPoolRead = true
    log(string.format(
      "[POOL_CD_READ] frame=%d LBA=$%06X sectors_lo=$%02X sectors_hi=$%02X " ..
      "dest=$%02X%02X mode=$%02X %s",
      frame, lba, dp8(0xF8), dp8(0xF9), dp8(0xFB), dp8(0xFA), dp8(0xFF),
      mpr_string()
    ))
  end
end

local function renderer_hit()
  if sawRedirect then
    rendererAfterRedirect = rendererAfterRedirect + 1
    sawRenderer = true
    log(string.format(
      "[RENDER_AFTER_REDIRECT] frame=%d cell=%02X %02X row=$%02X col=$%02X %s",
      frame, dp8(0x03), dp8(0x02), dp8(0x2F), dp8(0x30), mpr_string()
    ))
  end
end

open_log()
log(string.format(
  "External-pool trace armed. Pool LBA range $%X-$%X.",
  POOL_FIRST_LBA, POOL_LAST_LBA
))

for _, parser in ipairs(parsers) do
  emu.addMemoryCallback(
    function() parser_hit(parser.name) end,
    emu.callbackType.exec,
    parser.pc,
    parser.pc,
    CPU,
    MEM
  )
end

emu.addMemoryCallback(
  cd_read_hit,
  emu.callbackType.exec,
  0xE009,
  0xE009,
  CPU,
  MEM
)

emu.addMemoryCallback(
  renderer_hit,
  emu.callbackType.exec,
  0x5915,
  0x5915,
  CPU,
  MEM
)

emu.addEventCallback(function()
  frame = frame + 1
  if frame % 1800 == 0 then
    log(string.format(
      "[heartbeat] frame=%d parsers=%d redirects=%d pool_reads=%d native=%d renders=%d",
      frame, parserHits, redirectHits, poolReads, nativeHits, rendererAfterRedirect
    ))
  end
end, emu.eventType.endFrame)

emu.addEventCallback(function()
  local certified =
    sawRedirect and sawPoolRead and sawNative and sawRenderer and sawCleanReturn
  log("=== EXTERNAL POOL CERTIFICATION SUMMARY ===")
  log(string.format("parser_hits=%d", parserHits))
  log(string.format("redirect_hits=%d", redirectHits))
  log(string.format("pool_reads=%d", poolReads))
  log(string.format("native_segment_hits=%d", nativeHits))
  log(string.format("renderer_after_redirect=%d", rendererAfterRedirect))
  log(string.format("clean_control_return=%s", tostring(sawCleanReturn)))
  log(string.format("CERTIFIED=%s", tostring(certified)))
  if logFile then
    logFile:flush()
    logFile:close()
    logFile = nil
  end
end, emu.eventType.scriptEnded)
