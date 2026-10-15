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
local rejectedHits = {}

local targets = {
  {name="outer_event_entry", address=0xD800, guard={address=0xD800, bytes={0x4C,0x4B,0xD8}}},
  {name="exploration_loop", address=0x4000},
  {name="transition_promote", address=0x403D},
  {name="interaction_scan", address=0x4B20},
  {name="interaction_copy_entry_pre_write", address=0x4BD8,
   guard={address=0x4BD8, bytes={0x82,0xB1,0x24,0x9D,0x03,0x37}}},
  {name="interaction_copy_completed", address=0x4BE4,
   guard={address=0x4BD8, bytes={0x82,0xB1,0x24,0x9D,0x03,0x37}}},
  {name="object_init", address=0x5519,
   guard={address=0x5519, bytes={0x9C,0x80,0x27,0x20,0x3B,0x55}}},
  {name="object_init_completed", address=0x553A,
   guard={address=0x5519, bytes={0x9C,0x80,0x27,0x20,0x3B,0x55}}},
  {name="object_frame_update", address=0x55E9,
   guard={address=0x55E9, bytes={0xAD,0x7D,0x27,0x8D,0x80,0x27}}},
  {name="object_frame_update_completed", address=0x5602,
   guard={address=0x55E9, bytes={0xAD,0x7D,0x27,0x8D,0x80,0x27}}},

  -- Reusable ADPCM driver.
  {name="adpcm_voice_start", address=0x8108},
  {name="adpcm_completion_poll", address=0x837A},
  {name="adpcm_record_lookup", address=0x8471},

  -- System Card entry points used by this game.
  {name="bios_cd_read", address=0xE009},
  {name="bios_bm_free", address=0xE04B},
  {name="bios_bm_read", address=0xE04E},
  {name="bios_bm_write", address=0xE051},
  -- Call-site continuations *after* BM_READ returns: not BIOS-entry snapshots.
  {name="startup_bm_read_return", address=0x67C3,
   guard={address=0x67C0, bytes={0x20,0x4E,0xE0,0x1A,0x0A,0xAA}}},
  {name="mission_bm_read_return", address=0x604F,
   guard={address=0x604C, bytes={0x20,0x4E,0xE0,0x1A,0x0A,0xAA}}},
}

local function r8(address)
  return emu.read(address, MEM)
end

-- Code-address overlap between overlays is common. Validate mapped opcode
-- bytes before attributing any CPU-PC callback to this specific game routine.
-- These signatures were read directly from the authenticated original IMG.
local function guard_matches(target)
  if not target.guard then return true end
  for offset, expected in ipairs(target.guard.bytes) do
    if r8(target.guard.address + offset - 1) ~= expected then return false end
  end
  return true
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
  if not guard_matches(target) then
    rejectedHits[target.name] = (rejectedHits[target.name] or 0) + 1
    return
  end
  local c = cpu()
  hitCounts[target.name] = (hitCounts[target.name] or 0) + 1
  -- Exec hooks fire before an instruction. Copy entry and BIOS calls are
  -- deliberately named pre-write/pre-return so stale buffers are not
  -- mistaken for completed interaction or save data.
  local phase = "instruction_entry"
  if target.name == "interaction_copy_entry_pre_write" then
    phase = "before_interaction_copy"
  elseif target.name == "interaction_copy_completed" then
    phase = "after_ninth_copy_before_rts"
  elseif target.name == "object_init_completed" then
    phase = "after_object_initialization_before_rts"
  elseif target.name == "object_frame_update_completed" then
    phase = "after_object_update_before_rts"
  elseif target.name == "bios_bm_read" then
    phase = "before_bios_read"
  elseif target.name == "startup_bm_read_return"
      or target.name == "mission_bm_read_return" then
    phase = "after_bios_read_return"
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
  if target.name == "object_init" or target.name == "object_frame_update"
      or target.name == "object_init_completed"
      or target.name == "object_frame_update_completed" then
    -- A bounded sample plus count: these are instruction-entry snapshots,
    -- not claims that the current object update has finished.
    log(string.format(
      "[object_snapshot] count=$%02X first_live_2783=[%s] scratch_2823=[%s]",
      r8(0x277D), bytes_string(0x2783, 16), bytes_string(0x2823, 16)
    ))
  end
  if target.name == "bios_bm_read" or target.name == "bios_bm_write"
      or target.name == "startup_bm_read_return"
      or target.name == "mission_bm_read_return" then
    -- $2E91 is the startup reader's destination; $268F is the mission
    -- reader's buffer. A BIOS entry callback cannot prove completed I/O.
    log(string.format(
      "[bram_snapshot] phase=%s boot_status=$%02X boot_2E91=[%s] " ..
      "mission_status=$%02X mission_268F=[%s] %s",
      phase, r8(0x2E90), bytes_string(0x2E91, 4),
      r8(0x268E), bytes_string(0x268F, 4), mpr_string()
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
    log(string.format("%s=%d rejected_by_opcode_guard=%d",
      target.name, hitCounts[target.name] or 0, rejectedHits[target.name] or 0))
  end
  if logFile then
    logFile:flush()
    logFile:close()
    logFile = nil
  end
end, emu.eventType.scriptEnded)
