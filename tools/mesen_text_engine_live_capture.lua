-- Cyber City Oedo 808 - game-wide text-engine live capture
-- Mesen 2.2.1 / PC Engine CD
--
-- READ ONLY: this script does not modify RAM, MPRs, VRAM, disc state, or the
-- System Card. It records logical-PC landmarks together with all eight MPRs so
-- reused addresses can be assigned to the correct physical overlay.
--
-- Enable Script Window -> Settings -> Allow I/O and OS access to retain the
-- persistent log. The file is written to the script data directory as
-- cyber_oedo_text_engine_live.log.

local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory

local frame = 0
local logFile = nil
local hitCounts = {}

local targets = {
  -- Common dialogue parser entries: M0-A, M0-B, M1 ... M8.
  {name="dialogue_parser_M0_A_or_M8", address=0x94A7, pointer=0x007F},
  {name="dialogue_parser_M0_B", address=0x9543, pointer=0x007F},
  {name="dialogue_parser_M1",   address=0x95AA, pointer=0x007F},
  {name="dialogue_parser_M2",   address=0x95AE, pointer=0x007F},
  {name="dialogue_parser_M3",   address=0x9580, pointer=0x007F},
  {name="dialogue_parser_M4",   address=0x950E, pointer=0x007F},
  {name="dialogue_parser_M5",   address=0x9581, pointer=0x007F},
  {name="dialogue_parser_M6",   address=0x9526, pointer=0x007F},
  {name="dialogue_parser_M7",   address=0x94A8, pointer=0x007F},
  -- M8 reuses $94A7; the shared callback name and MPRs disambiguate it.

  -- Shared stock dialogue renderer and font path.
  {name="dialogue_renderer", address=0x5915},
  {name="dialogue_font_fetch", address=0x56C0},

  -- Information-page dispatcher variants.
  {name="info_dispatch_early_A", address=0x9B1D, pointer=0x0005},
  {name="info_dispatch_early_B", address=0x59E2, pointer=0x0000},
  {name="info_dispatch_early_C", address=0xC460, pointer=0x0000},
  {name="info_dispatch_common", address=0xB5C7, pointer=0x0000},

  -- ENDING mixed completion/save/credits path.
  {name="ending_mixed_dispatch", address=0x5D5C, pointer=0x0001},
  {name="ending_shiftjis_renderer", address=0x6D5E, pointer=0x0001},
  {name="ending_glyph_renderer", address=0x6E36},

  -- Common CD read entry for correlating overlay/resource loads.
  {name="system_cd_read", address=0xE009},
}

local function r8(address)
  return emu.read(address, MEM)
end

local function r16(address)
  return emu.read16(address, MEM, false)
end

local function cpu()
  local c = emu.getCpuState(CPU)
  return {
    pc = c.pc or 0,
    a = c.a or 0,
    x = c.x or 0,
    y = c.y or 0,
    sp = c.sp or 0,
    ps = c.ps or 0,
  }
end

local function mprs()
  local state = emu.getState()
  local result = {}
  for i=0,7 do
    result[i] = state["memoryManager.mpr[" .. i .. "]"] or 0
  end
  return result
end

local function mpr_string()
  local values = mprs()
  local parts = {}
  for i=0,7 do
    parts[#parts+1] = string.format("MPR%d=$%02X", i, values[i])
  end
  return table.concat(parts, " ")
end

local function open_log()
  if type(io) ~= "table" or type(io.open) ~= "function" then
    return
  end
  local base = emu.getScriptDataFolder()
  if not base or base == "" then
    return
  end
  logFile = io.open(base .. "/cyber_oedo_text_engine_live.log", "a")
  if logFile then
    logFile:write("\n=== NEW TEXT ENGINE LIVE SESSION ===\n")
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

local function describe_pointer(address)
  if not address then
    return ""
  end
  local pointer = r16(address)
  local b0 = r8(pointer)
  local b1 = r8((pointer + 1) & 0xFFFF)
  local b2 = r8((pointer + 2) & 0xFFFF)
  return string.format(
    " ptrvar=$%04X ptr=$%04X next=%02X %02X %02X",
    address, pointer, b0, b1, b2
  )
end

local function hit(target)
  local c = cpu()
  hitCounts[target.name] = (hitCounts[target.name] or 0) + 1
  log(string.format(
    "[%s #%d] frame=%d PC=$%04X A=$%02X X=$%02X Y=$%02X SP=$%02X " ..
    "cursor=(row=$%02X,col=$%02X) voice=$%02X joy=$%02X trg=$%02X%s %s",
    target.name,
    hitCounts[target.name],
    frame,
    c.pc,
    c.a,
    c.x,
    c.y,
    c.sp,
    r8(0x002F),
    r8(0x0030),
    r8(0x37F1),
    r8(0x2228),
    r8(0x222D),
    describe_pointer(target.pointer),
    mpr_string()
  ))
end

open_log()
log("Cyber City Oedo 808 game-wide text-engine capture armed.")
log("Read-only instrumentation: YES")

for _, target in ipairs(targets) do
  emu.addMemoryCallback(
    function() hit(target) end,
    emu.callbackType.exec,
    target.address,
    target.address,
    CPU,
    MEM
  )
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame % 600 == 0 then
    log(string.format("[heartbeat] frame=%d PC=$%04X %s", frame, cpu().pc, mpr_string()))
  end
end, emu.eventType.endFrame)

emu.addEventCallback(function()
  log("=== TEXT ENGINE LIVE SESSION SUMMARY ===")
  for _, target in ipairs(targets) do
    log(string.format("%s=%d", target.name, hitCounts[target.name] or 0))
  end
  if logFile then
    logFile:flush()
    logFile:close()
    logFile = nil
  end
end, emu.eventType.scriptEnded)
