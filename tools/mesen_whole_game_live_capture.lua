-- Cyber City Oedo 808 - whole-game runtime capture
-- Mesen 2.2.1 / PC Engine CD
--
-- Read-only instrumentation for whole-game architecture certification.
-- Records logical execution landmarks together with all eight HuC6280 MPRs,
-- persistent progress/save state, interaction handoff bytes, and object state.

local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory

local frame = 0
local logFile = nil
local hitCounts = {}

local targets = {
  {name="outer_event_entry", address=0xD800},
  {name="exploration_loop", address=0x4000},
  {name="transition_promote", address=0x403D},
  {name="interaction_scan", address=0x4B20},
  {name="interaction_copy_entry_pre_write", address=0x4BD8},
  {name="object_init", address=0x5519},
  {name="object_frame_update", address=0x55E9},

  -- Reusable ADPCM driver.
  {name="adpcm_voice_start", address=0x8108},
  {name="adpcm_completion_poll", address=0x837A},
  {name="adpcm_record_lookup", address=0x8471},

  -- System Card entry points used by this game.
  {name="bios_cd_read", address=0xE009},
  {name="bios_bm_free", address=0xE04B},
  {name="bios_bm_read", address=0xE04E},
  {name="bios_bm_write", address=0xE051},
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

local function bytes_string(address, count)
  local parts = {}
  for i=0,count-1 do
    parts[#parts+1] = string.format("%02X", r8((address + i) & 0xFFFF))
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
  logFile = io.open(base .. "/cyber_oedo_whole_game_live.log", "a")
  if logFile then
    logFile:write("\n=== NEW WHOLE GAME LIVE SESSION ===\n")
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

local function hit(target)
  local c = cpu()
  hitCounts[target.name] = (hitCounts[target.name] or 0) + 1
  -- Exec hooks fire before an instruction. Copy entry and BIOS calls are
  -- deliberately named pre-write/pre-return so stale buffers are not
  -- mistaken for completed interaction or save data.
  local phase = "instruction_entry"
  if target.name == "interaction_copy_entry_pre_write" then
    phase = "before_interaction_copy"
  elseif target.name == "bios_bm_read" then
    phase = "before_bios_read"
  end
  log(string.format(
    "[%s #%d] phase=%s frame=%d PC=$%04X A=$%02X X=$%02X Y=$%02X SP=$%02X " ..
    "progress=$%02X scene=%02X/%02X/%02X interaction=[%s] " ..
    "mission_save_buffer=[%s] voice=$%02X %s",
    target.name,
    hitCounts[target.name],
    phase,
    frame,
    c.pc,
    c.a,
    c.x,
    c.y,
    c.sp,
    r8(0x371F),
    r8(0x3700),
    r8(0x3701),
    r8(0x3702),
    bytes_string(0x3703, 9),
    bytes_string(0x268F, 4),
    r8(0x37F1),
    mpr_string()
  ))
  if target.name == "outer_event_entry" then
    -- Capture the actual mapped 64-byte controller window, not just the PC.
    -- The MPR log is required to authenticate this against the expected bank.
    log(string.format("[outer_event_code] D800=[%s] %s",
      bytes_string(0xD800, 64), mpr_string()))
  end
  if target.name == "object_init" or target.name == "object_frame_update" then
    -- A bounded sample plus count: these are instruction-entry snapshots,
    -- not claims that the current object update has finished.
    log(string.format(
      "[object_snapshot] count=$%02X first_live_2783=[%s] scratch_2823=[%s]",
      r8(0x277D), bytes_string(0x2783, 16), bytes_string(0x2823, 16)
    ))
  end
  if target.name == "bios_bm_read" or target.name == "bios_bm_write" then
    -- $2E91 is the startup reader's destination; $268F is the mission
    -- reader's buffer. A BIOS entry callback cannot prove completed I/O.
    log(string.format(
      "[bram_call_entry] boot_buffer_2E91=[%s] mission_buffer_268F=[%s]",
      bytes_string(0x2E91, 4), bytes_string(0x268F, 4)
    ))
  end
end

open_log()
log("Cyber City Oedo 808 whole-game capture armed.")
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
    log(string.format(
      "[heartbeat] frame=%d PC=$%04X progress=$%02X scene=%02X/%02X/%02X %s",
      frame,
      cpu().pc,
      r8(0x371F),
      r8(0x3700),
      r8(0x3701),
      r8(0x3702),
      mpr_string()
    ))
  end
end, emu.eventType.endFrame)

emu.addEventCallback(function()
  log("=== WHOLE GAME LIVE SESSION SUMMARY ===")
  for _, target in ipairs(targets) do
    log(string.format("%s=%d", target.name, hitCounts[target.name] or 0))
  end
  if logFile then
    logFile:flush()
    logFile:close()
    logFile = nil
  end
end, emu.eventType.scriptEnded)
