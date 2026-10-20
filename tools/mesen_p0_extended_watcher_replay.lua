-- Extended P0 natural street-watcher A/B replay, MesenCE 2.2.1.
-- READ ONLY. No savestate, forced PC, or memory mutation; only controller input.
-- Intended for original and portrait-only images in separate Mesen instances.
-- The initial input contract matches mesen_p0_natural_npc_regression.lua.
-- After frame 18000 pulse Button I to explore dialogue progression.
-- Observing identical frames is not proof of scene-return or ADPCM correctness.
local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory
local frame = 0
local hits = {}
local targets = {0x80E0, 0x8405, 0x4B20, 0x4012, 0x403D, 0xE036, 0xE039}
for _,address in ipairs(targets) do
  local pc = address
  hits[pc] = 0
  emu.addMemoryCallback(function()
    hits[pc] = hits[pc] + 1
  end, emu.callbackType.exec, pc, pc, CPU, MEM)
end
local function mprs()
  local state = emu.getState()
  local out = {}
  for i=0,7 do
    out[#out+1] = string.format("%02X",state["memoryManager.mpr["..i.."]"] or 0)
  end
  return table.concat(out," ")
end
local function capture()
  local filename = emu.getScriptDataFolder() .. "/extended_" .. frame .. ".png"
  local file = assert(io.open(filename,"wb"))
  file:write(emu.takeScreenshot())
  file:close()
end
emu.addEventCallback(function()
  frame = frame + 1
  if frame == 6000 or frame == 8600 or frame == 13300
     or frame == 15600 or (frame >= 16500 and frame % 500 == 0) then
    capture()
    local c = emu.getCpuState(CPU)
    print(string.format(
      "P0_EXT f=%d pc=%04X mprs=[%s] state=%02X,%02X,%02X "..
      "watcher=%d interaction=%d gameLoop=%d",
      frame,c.pc,mprs(),emu.read(0x3700,MEM),
      emu.read(0x3701,MEM),emu.read(0x3702,MEM),
      hits[0x8405],hits[0x4B20],hits[0x4012]
    ))
  end
  if frame == 26000 then
    print(string.format(
      "P0_EXT_RESULT adpcm=%d portrait=%d interact=%d "..
      "gameLoop=%d transition=%d AD_READ=%d AD_WRITE=%d",
      hits[0x80E0],hits[0x8405],hits[0x4B20],
      hits[0x4012],hits[0x403D],hits[0xE036],hits[0xE039]
    ))
    emu.stop(0)
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
  else
    input.right = true
  end
  emu.setInput(input,0)
end, emu.eventType.inputPolled)
