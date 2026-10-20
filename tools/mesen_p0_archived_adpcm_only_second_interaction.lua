-- MesenCE 2.2.1 isolated OLD ADPCM-only specimen replay; UNSAFE RESEARCH.
-- Runs only on a separately authored, authenticated throwaway ADPCM-only build.
-- Do not enable profile in main builder. No PC forcing, RAM writes or savestate.
-- This probe cannot certify other overlays or audio sample fidelity.
local frame=0
local CPU=emu.cpuType.pce
local MEM=emu.memType.pceMemory
local DEBUG=emu.memType.pceDebug
local adpcm=0
local portrait=0
local scan=0
local menuI=0
local cave_resident=0
local stock_portrait=0
local function hex(address,n)
  local result={}
  for i=0,n-1 do
    result[#result+1]=string.format("%02X",emu.read(address+i,DEBUG))
  end
  return table.concat(result," ")
end
local function mprs()
  local state=emu.getState()
  local parts={}
  for i=0,7 do
    parts[#parts+1]=string.format("%02X",
      assert(state["memoryManager.mpr["..i.."]"]))
  end
  return table.concat(parts," ")
end
emu.addMemoryCallback(function()
  adpcm=adpcm+1
  local call=hex(0x80E0,3)
  local cave=hex(0x4CFA,8)
  if call=="20 FA 4C" and cave=="43 20 48 43 40 48 A9 6B" then
    cave_resident=cave_resident+1
  end
  print(string.format("P0_OLD_ADPCM f=%d call=[%s] cave=[%s] safe_prefix=%s",
    frame,call,cave,tostring(cave_resident==adpcm)))
end,emu.callbackType.exec,0x80E0,0x80E0,CPU,MEM)
emu.addMemoryCallback(function()
  portrait=portrait+1
  if hex(0x8405,3)=="20 09 E0" then
    stock_portrait=stock_portrait+1
  end
end,emu.callbackType.exec,0x8405,0x8405,CPU,MEM)
emu.addMemoryCallback(function() scan=scan+1 end,
  emu.callbackType.exec,0x4B20,0x4B20,CPU,MEM)
emu.addMemoryCallback(function() menuI=menuI+1 end,
  emu.callbackType.exec,0x5B95,0x5B95,CPU,MEM)
emu.addEventCallback(function()
  frame=frame+1
  if frame==15600 or frame==17500 or frame==17670 or frame==17760 or
     frame==23000 or frame==23400 or frame==23500 or frame==23600 or
     frame==23700 or frame==24000 or frame==26000 then
    local filename=string.format("archived_adpcm_only_%d.png",frame)
    local file=assert(io.open(emu.getScriptDataFolder().."/"..filename,"wb"))
    file:write(emu.takeScreenshot())
    file:close()
    print(string.format("P0_OLD_STATE f=%d pc=%04X mprs=[%s] ADPCM=%d portrait=%d scan=%d",
      frame,emu.getCpuState(CPU).pc,mprs(),adpcm,portrait,scan))
  end
  if frame==26000 then
    local success=adpcm==3 and cave_resident==3 and
      portrait==2 and stock_portrait==2 and
      scan==20 and menuI==3 and mprs()=="FF F8 80 81 82 83 84 00"
    print(string.format(
      "P0_OLD_RESULT adpcm=%d cave_resident=%d portrait=%d stock_portrait=%d scan=%d menuI=%d success=%s",
      adpcm,cave_resident,portrait,stock_portrait,scan,menuI,tostring(success)))
    emu.stop(success and 0 or 9)
  end
end,emu.eventType.endFrame)
emu.addEventCallback(function()
  local input={}
  if frame<8600 then
    input.run=frame<600 and frame%120<10
    input.i=frame>=600 and frame%30<5
  elseif frame<13300 then input.right=true
  elseif frame<15600 then input.up=true
  elseif frame<16000 then
    input.right=true; input.i=frame%20<3
  elseif frame<17500 then input.right=true
  elseif frame>=17600 and frame<17610 then input.up=true
  elseif frame>=17700 and frame<17710 then input.i=true
  elseif frame>=23000 and frame<23110 then input.right=true
  elseif frame>=23110 and frame<23500 then input.i=frame%40<7
  end
  emu.setInput(input,0)
end,emu.eventType.inputPolled)
