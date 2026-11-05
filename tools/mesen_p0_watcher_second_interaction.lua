-- MesenCE 2.2.1 read-only cold-boot watcher return and second interaction.
-- Execute separately on authenticated original and portrait-only discs.
-- Original and patched builds receive IDENTICAL ordinary controller input.
-- No PC forcing, RAM mutation, savestate, or unsafe ADPCM profile.
local frame = 0
local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory
local hits = {}
local watched = {0x80E0,0x8405,0x4B20,0x5B95,0x5BD3,0x4012,0x403D,0xE036,0xE039}
for _,pc in ipairs(watched) do
  local address = pc
  hits[address] = 0
  emu.addMemoryCallback(function()
    hits[address] = hits[address] + 1
  end, emu.callbackType.exec, address, address, CPU, MEM)
end
local function mprs()
  local state, out = emu.getState(), {}
  for i=0,7 do
    out[#out+1] = string.format("%02X",
      assert(state["memoryManager.mpr["..i.."]]))
  end
  return table.concat(out," ")
end
local function snapshot()
  local name = string.format("second_interaction_%d.png",frame)
  local file = assert(io.open(emu.getScriptDataFolder().."/"..name,"wb"))
  file:write(emu.takeScreenshot())
  file:close()
  print(string.format(
    "P0_SECOND f=%d pc=%04X mprs=[%s] keys=%02X,%02X adpcm=%d portrait=%d scan=%d menuI=%d menuII=%d loop=%d transition=%d AD_READ=%d AD_WRITE=%d",
    frame, emu.getCpuState(CPU).pc, mprs(),
    emu.read(0x222C,MEM), emu.read(0x222D,MEM),
    hits[0x80E0],hits[0x8405],hits[0x4B20],
    hits[0x5B95],hits[0x5BD3],hits[0x4012],
    hits[0x403D],hits[0xE036],hits[0xE039]
  ))
end
emu.addEventCallback(function()
  frame = frame + 1
  if frame==6000 or frame==8600 or frame==13300 or frame==15600 or
     frame==17500 or frame==17670 or frame==17760 or frame==17900 or
     (frame>=18000 and frame%500==0) or
     (frame>=23000 and frame<=24500 and frame%100==0) then
    snapshot()
  end
  if frame==26000 then
    local success =
      hits[0x80E0] == 3 and hits[0x8405] == 2 and
      hits[0x4B20] == 20 and hits[0x5B95] == 3 and
      hits[0x5BD3] == 0 and
      mprs() == "FF F8 80 81 82 83 84 00"
    print(string.format(
      "P0_SECOND_RESULT adpcm=%d portrait=%d scan=%d menuI=%d menuII=%d mprs=[%s] success=%s",
      hits[0x80E0],hits[0x8405],hits[0x4B20],hits[0x5B95],
      hits[0x5BD3],mprs(),tostring(success)
    ))
    -- Success certifies only this input route and hook-count invariants.
    -- It does not certify audio fidelity, ADPCM caching, or all missions.
    emu.stop(success and 0 or 9)
  end
end,emu.eventType.endFrame)
emu.addEventCallback(function()
  local input = {}
  if frame < 8600 then
    input.run = frame < 600 and frame % 120 < 10
    input.i = frame >= 600 and frame % 30 < 5
  elseif frame < 13300 then
    input.right = true
  elseif frame < 15600 then
    input.up = true
  elseif frame < 16000 then
    input.right = true
    input.i = frame % 20 < 3
  elseif frame < 17500 then
    input.right = true
  elseif frame >= 17600 and frame < 17610 then
    input.up = true -- choose "Move" in watcher command menu
  elseif frame >= 17700 and frame < 17710 then
    input.i = true -- confirm Move, exit watcher to street
  elseif frame >= 23000 and frame < 23110 then
    input.right = true -- approach watcher again from the street
  elseif frame >= 23110 and frame < 23500 then
    input.i = frame % 40 < 7 -- interact, then STOP advancing text
  end
  emu.setInput(input,0)
end,emu.eventType.inputPolled)
