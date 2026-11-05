-- Read-only Mission-0 street-watcher dialogue-exit exploration, MesenCE 2.2.1.
-- This is a DIAGNOSTIC, not a certified input replay. Do not promote a
-- successful process exit to a successful second interaction.
-- Never modifies game RAM, forces PC, or loads a savestate.
local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory
local frame = 0
local count = {adpcm=0, portrait=0, scan=0}
for _, item in ipairs({
  {0x80E0,"adpcm"}, {0x8405,"portrait"}, {0x4B20,"scan"}
}) do
  local pc, name = item[1], item[2]
  emu.addMemoryCallback(function()
    count[name] = count[name] + 1
    if frame >= 15000 then
      print(string.format("P0_EXIT_HOOK f=%d name=%s hits=%d",frame,name,count[name]))
    end
  end, emu.callbackType.exec, pc, pc, CPU, MEM)
end
local function mprs()
  local state = emu.getState()
  local result = {}
  for i=0,7 do
    local value = assert(state["memoryManager.mpr["..i.."]])
    result[#result+1] = string.format("%02X",value)
  end
  return table.concat(result," ")
end
emu.addEventCallback(function()
  frame = frame + 1
  if frame == 15600 or frame == 16000 or
    (frame >= 18000 and frame % 1000 == 0) then
    local file = assert(io.open(
      emu.getScriptDataFolder().."/dialogue_exit_"..frame..".png","wb"))
    file:write(emu.takeScreenshot())
    file:close()
    local c = emu.getCpuState(CPU)
    print(string.format(
      "P0_EXIT f=%d pc=%04X mprs=[%s] state=%02X,%02X,%02X adpcm=%d portrait=%d scan=%d",
      frame,c.pc,mprs(),emu.read(0x3700,MEM),
      emu.read(0x3701,MEM),emu.read(0x3702,MEM),
      count.adpcm,count.portrait,count.scan
    ))
  end
  if frame == 38000 then
    local second = count.portrait >= 2 and count.adpcm >= 3
    print(string.format(
      "P0_EXIT_RESULT second_portrait_and_audio=%s adpcm=%d portrait=%d scan=%d",
      tostring(second),count.adpcm,count.portrait,count.scan
    ))
    -- Explicitly fail if the follow-up has not triggered a second load.
    -- Even success here needs a separate original/portrait parity comparison.
    emu.stop(second and 0 or 9)
  end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local input = {}
  if frame < 8600 then
    input.run = frame < 600 and frame % 120 < 10
    input.i = frame >= 600 and frame % 30 < 5
  elseif frame < 13300 then
    input.right = true
  elseif frame < 15600 then
    input.up = true
  elseif frame < 18000 then
    input.right = true
    input.i = frame < 16000 and frame % 20 < 3
  elseif frame < 24000 then
    input.i = frame % 25 < 4
  elseif frame < 26000 then
    input.right = true
  elseif frame < 28000 then
    -- Probe dismissal/back; unlike the earlier replay, exercise Button II.
    input.ii = frame % 35 < 4
  elseif frame < 30000 then
    -- Probe a choice move followed by confirm.
    input.down = frame % 60 < 5
    input.i = frame % 60 >= 20 and frame % 60 < 25
  elseif frame < 32000 then
    input.run = frame % 60 < 5
    input.ii = frame % 60 >= 20 and frame % 60 < 25
  else
    input.right = true
    input.i = frame % 25 < 4
  end
  emu.setInput(input,0)
end, emu.eventType.inputPolled)
