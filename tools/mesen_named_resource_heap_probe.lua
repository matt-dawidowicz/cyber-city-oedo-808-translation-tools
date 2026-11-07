-- Cyber City Oedo 808 / MesenCE 2.2.1
-- Read-only Mission 0-B named-resource and heap probe.
--
-- Logs every named-resource load through the M0-B loader ($6CCB), the
-- descriptor fields installed by the $6E36 lookup, the bump-heap pointer
-- ($2778/$2779) before and after each load, and heap compaction ($9BBA).
--
-- Hooks are guarded by the exact source bytes at each address so a different
-- overlay mapped at the same logical address is not misattributed.
-- No PC, RAM, or savestate shortcuts are used; controller input matches the
-- opening schedule of mesen_p0_natural_npc_regression.lua.
--
-- Run with: Mesen --testRunner game.cue mesen_named_resource_heap_probe.lua
--             --enableStdout --pcEngine.port1.type=PceController
-- Lua I/O must be allowed for screenshots.

local CPU = emu.cpuType.pce
local DEBUG = emu.memType.pceDebug
local STOP_FRAME = 8700
local SHOT_FRAMES = {[3000]=true, [4500]=true, [5000]=true, [5200]=true,
  [5400]=true, [6000]=true, [7000]=true, [8000]=true, [8600]=true}
local frame = 0
local loads = 0
local compactions = 0
local kuruzer_loaded = false

local function byte(address)
  return emu.read(address, DEBUG)
end

local function word(address)
  return byte(address) + byte(address + 1) * 256
end

-- The HuC6280 zero page is RAM page $F8 mapped at logical $2000.
local function zp_word(address)
  return word(0x2000 + address)
end

local function hex(address, count)
  local parts = {}
  for offset = 0, count - 1 do
    parts[#parts + 1] = string.format("%02X", byte(address + offset))
  end
  return table.concat(parts, " ")
end

local function name_at(address)
  local chars = {}
  for offset = 0, 9 do
    local value = byte(address + offset)
    if value == 0 then break end
    chars[#chars + 1] = string.char(value)
  end
  return table.concat(chars)
end

local function mpr_string()
  local state = emu.getState()
  local parts = {}
  for i = 0, 7 do
    parts[#parts + 1] = string.format("%02X", state["memoryManager.mpr[" .. i .. "]"])
  end
  return table.concat(parts, " ")
end

local function trace(label, extra)
  local c = emu.getCpuState(CPU)
  print(string.format("RES_HEAP %s f=%d pc=%04X mprs=[%s] %s",
    label, frame, c.pc, mpr_string(), extra or ""))
end

local function guarded(address, expected, callback)
  emu.addMemoryCallback(function()
    if hex(address, #expected // 3 + 1) == expected then
      callback()
    end
  end, emu.callbackType.exec, address, address, CPU, emu.memType.pceMemory)
end

-- $8F9A: JSR $6CCB with name pointer in $08/$09 and heap pointer in $06/$07.
guarded(0x8F9A, "20 CB 6C", function()
  loads = loads + 1
  local name = name_at(zp_word(0x08))
  if name == "KURUZER" then kuruzer_loaded = true end
  trace("load_request", string.format("n=%d name=%s heap=%04X",
    loads, name, word(0x2778)))
end)

-- $6D7C: JSR $6EA0 after lookup; descriptor fields are installed.
guarded(0x6D7C, "20 A0 6E", function()
  trace("load_descriptor", string.format(
    "dest=%04X lba=%02X%02X%02X len=%04X",
    zp_word(0x00), byte(0x29CA), byte(0x29CB), byte(0x29CC), word(0x29CE)))
end)

-- $8F9D: return from $6CCB; $06/$07 is the next heap pointer or zero.
guarded(0x8F9D, "A5 06 05 07", function()
  trace("load_result", string.format("next_heap=%04X", zp_word(0x06)))
end)

guarded(0x9BBA, "A9 A9 85 02", function()
  compactions = compactions + 1
  trace("heap_compaction", string.format("n=%d heap=%04X", compactions, word(0x2778)))
end)

emu.addEventCallback(function()
  frame = frame + 1
  if SHOT_FRAMES[frame] then
    local name = string.format("frame_%d.png", frame)
    local file = assert(io.open(emu.getScriptDataFolder() .. "/" .. name, "wb"))
    file:write(emu.takeScreenshot())
    file:close()
    trace("screenshot", name)
  end
  if frame == STOP_FRAME then
    trace("result", string.format("loads=%d compactions=%d kuruzer_loaded=%s heap=%04X",
      loads, compactions, tostring(kuruzer_loaded), word(0x2778)))
    emu.stop(kuruzer_loaded and 0 or 9)
  end
end, emu.eventType.endFrame)

emu.addEventCallback(function()
  local input = {}
  if frame < 8600 then
    input.run = frame < 600 and frame % 120 < 10
    input.i = frame >= 600 and frame % 30 < 5
  end
  emu.setInput(input, 0)
end, emu.eventType.inputPolled)
