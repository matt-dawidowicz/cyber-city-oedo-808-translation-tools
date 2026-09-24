-- Cyber City Oedo 808 - Mission 0 packed-English renderer capture
-- Mesen 2.2.1 / PC Engine CD
--
-- READ ONLY.  This script certifies the narrow renderer proof without
-- modifying RAM, MPRs, VRAM, disc state, or System Card state.
--
-- Expected proof path for a packed English glyph:
--   $56C0  stock font-fetch call site
--   $A800  explicitly loaded packed-English hook
--   $56C3  return to untouched stock renderer
--
-- The runtime-write watch covers $A800-$BBAF. Initial loader writes are
-- expected; writes after the extended $A400 loader completes are evidence of
-- an ownership collision and must be investigated.
--
-- The script records $F9/$F8 (lead/trail), MPRs, cursor state, and the complete
-- 32-byte $4C6C glyph staging cell after the hook returns.

local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory

local frame = 0
local logFile = nil
local hits = {pre=0, hook=0, post=0, private=0, stock=0, runtimeWrites=0}

local function r8(address)
  return emu.read(address, MEM)
end

local function cpu()
  local c = emu.getCpuState(CPU)
  return {
    pc = c.pc or 0,
    a = c.a or 0,
    x = c.x or 0,
    y = c.y or 0,
    sp = c.sp or 0,
  }
end

local function mprs()
  local state = emu.getState()
  local values = {}
  for i=0,7 do
    values[i] = state["memoryManager.mpr[" .. i .. "]"] or 0
  end
  return values
end

local function mpr_string()
  local values = mprs()
  local parts = {}
  for i=0,7 do
    parts[#parts+1] = string.format("MPR%d=$%02X", i, values[i])
  end
  return table.concat(parts, " ")
end

local function staging_string()
  local parts = {}
  for offset=0,31 do
    parts[#parts+1] = string.format("%02X", r8(0x4C6C + offset))
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
  logFile = io.open(base .. "/cyber_oedo_packed_english_live.log", "a")
  if logFile then
    logFile:write("\n=== NEW PACKED ENGLISH SESSION ===\n")
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

local function describe(tag)
  local c = cpu()
  local lead = r8(0x00F9)
  local trail = r8(0x00F8)
  local private = lead >= 0xF0 and lead <= 0xFC
  log(string.format(
    "[%s] frame=%d PC=$%04X A=$%02X X=$%02X Y=$%02X SP=$%02X " ..
    "glyph=%02X %02X private=%s cursor=(%02X,%02X) %s",
    tag, frame, c.pc, c.a, c.x, c.y, c.sp,
    lead, trail, private and "yes" or "no",
    r8(0x002F), r8(0x0030), mpr_string()
  ))
  return private
end

open_log()
log("Cyber City Oedo 808 packed-English Mission 0 capture armed.")
log("Read-only instrumentation: YES")

emu.addMemoryCallback(
  function()
    hits.pre = hits.pre + 1
    if describe("font_fetch_pre") then
      hits.private = hits.private + 1
    else
      hits.stock = hits.stock + 1
    end
  end,
  emu.callbackType.exec,
  0x56C0, 0x56C0, CPU, MEM
)

emu.addMemoryCallback(
  function()
    hits.hook = hits.hook + 1
    describe("packed_hook")
  end,
  emu.callbackType.exec,
  0xA800, 0xA800, CPU, MEM
)

emu.addMemoryCallback(
  function()
    hits.post = hits.post + 1
    local private = describe("font_fetch_post")
    if private then
      log("[staging] " .. staging_string())
    end
  end,
  emu.callbackType.exec,
  0x56C3, 0x56C3, CPU, MEM
)

emu.addMemoryCallback(
  function(address, value)
    hits.runtimeWrites = hits.runtimeWrites + 1
    if hits.runtimeWrites <= 32 then
      local c = cpu()
      log(string.format(
        "[runtime_write #%d] frame=%d addr=$%04X value=$%02X PC=$%04X %s",
        hits.runtimeWrites, frame, address, value or 0, c.pc, mpr_string()
      ))
    end
  end,
  emu.callbackType.write,
  0xA800, 0xBBAF, CPU, MEM
)

emu.addEventCallback(function()
  frame = frame + 1
  if frame % 600 == 0 then
    log(string.format(
      "[heartbeat] frame=%d PC=$%04X pre=%d hook=%d post=%d private=%d stock=%d %s",
      frame, cpu().pc, hits.pre, hits.hook, hits.post,
      hits.private, hits.stock, mpr_string()
    ))
  end
end, emu.eventType.endFrame)

emu.addEventCallback(function()
  log("=== PACKED ENGLISH SESSION SUMMARY ===")
  log(string.format(
    "pre=%d hook=%d post=%d private=%d stock=%d runtime_writes=%d",
    hits.pre, hits.hook, hits.post, hits.private, hits.stock, hits.runtimeWrites
  ))
  if logFile then
    logFile:flush()
    logFile:close()
    logFile = nil
  end
end, emu.eventType.scriptEnded)
