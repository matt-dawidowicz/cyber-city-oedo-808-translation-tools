-- Cyber City Oedo 808 / MesenCE 2.2.1
-- P0 cold-boot *natural NPC* regression: no forced PC, RAM writes, or savestate.
--
-- This visits the street and interacts with the watcher (NOT the bartender).
-- Run against authenticated original media and against the release-disabled
-- --english-pilot --vwf-pilot disc with performance_experiment=none.
-- The comparison is a control for #46, not Mission-0-B certification (#45).
--
-- The zero bytes at $4CFA in an UNPATCHED run are only a baseline check;
-- they do NOT prove a cache-patched image maps zero bytes there. Run
-- separate legacy-patched comparisons to assess actual code residency.
-- Requires Mesen --testRunner with Lua file I/O enabled for PNG screenshots.
-- Run separately for each disc from separate empty work directories.

local CPU = emu.cpuType.pce
local DEBUG = emu.memType.pceDebug
local frame = 0
local hits = {}
local late_adpcm = 0
local late_portrait = 0
local unpatched_baseline_confirmed = false

local function byte(address)
  return emu.read(address, DEBUG)
end

local function hex(address, count)
  local parts = {}
  for offset=0,count-1 do
    parts[#parts+1] = string.format("%02X", byte(address+offset))
  end
  return table.concat(parts, " ")
end

local function mpr_string()
  local state = emu.getState()
  local parts = {}
  for i=0,7 do
    local mpr = state["memoryManager.mpr["..i.."]"]
    assert(mpr ~= nil, "MPR missing: "..i)
    parts[#parts+1] = string.format("%02X", mpr)
  end
  return table.concat(parts, " ")
end

local function trace(label, extra)
  local c = emu.getCpuState(CPU)
  print(string.format(
    "P0_NPC %s f=%d pc=%04X mprs=[%s] %s",
    label, frame, c.pc, mpr_string(), extra or ""
  ))
end

local hooks = {0x80E0, 0x8405, 0x4B20, 0x4BD8, 0x4BE4}
for _, address in ipairs(hooks) do
  local pc = address
  hits[pc] = 0
  emu.addMemoryCallback(function()
    hits[pc] = hits[pc] + 1
    if pc == 0x80E0 then
      local call = hex(0x80E0, 3)
      local target = hex(0x4CFA, 12)
      if frame > 15000 then
        late_adpcm = late_adpcm + 1
        if call == "20 33 E0"
           and target == "00 00 00 00 00 00 00 00 00 00 00 00" then
          unpatched_baseline_confirmed = true
        end
        trace("shared_ADPCM_call", "call=["..call.."] 4CFA=["..target.."]")
      end
    elseif pc == 0x8405 and frame > 15000 then
      late_portrait = late_portrait + 1
      trace("natural_NPC_portrait_loader")
    elseif frame > 15000 and hits[pc] <= 25 then
      trace(string.format("exec_%04X",pc))
    end
  end, emu.callbackType.exec, pc, pc, CPU, emu.memType.pceMemory)
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame == 6000 or frame == 8600 or frame == 13300
     or frame == 15600 or frame == 16500 or frame == 17000
     or frame == 17800 then
    local name = string.format("snapshot_%d.png", frame)
    local file = assert(io.open(name, "wb"))
    file:write(emu.takeScreenshot())
    file:close()
    trace("screenshot",name)
  end
  if frame == 17900 then
    local good = late_adpcm > 0 and late_portrait > 0
      and unpatched_baseline_confirmed
    trace("result",string.format(
      "late_ADPCM=%d natural_portrait=%d unpatched_baseline=%s success=%s",
      late_adpcm, late_portrait, tostring(unpatched_baseline_confirmed),
      tostring(good)
    ))
    emu.stop(good and 0 or 9)
  end
end, emu.eventType.endFrame)

-- Original-game controller input only. The timings are intentionally explicit
-- and must not be silently retuned to make a patched disc appear to pass.
emu.addEventCallback(function()
  local input = {}
  if frame < 8600 then
    input.run = frame < 600 and frame % 120 < 10
    input.i = frame >= 600 and frame % 30 < 5
  elseif frame < 13300 then
    input.right = true
  elseif frame < 15600 then
    input.up = true
  else
    input.right = true
    input.i = frame % 20 < 3
  end
  emu.setInput(input, 0)
end, emu.eventType.inputPolled)
