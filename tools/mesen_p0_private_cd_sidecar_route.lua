-- MesenCE 2.2.1 read-only disposable CD-sidecar combined-cache replay.
-- Never use this with stock disc: the $80AF helper only exists in a throwaway
-- source-authenticated candidate built by adpcm_cd_sidecar_candidate.py.
-- Input timings are experimental and may miss the second NPC; FAIL if so.
local CPU=emu.cpuType.pce
local MEM=emu.memType.pceMemory
local DBG=emu.memType.pceDebug
local frame=0
local hits={stub=0,sidecar=0,cache=0,portrait=0,scan=0,menu=0}
local function hex(addr,count)
  local out={}
  for i=0,count-1 do
    out[#out+1]=string.format("%02X",emu.read(addr+i,DBG))
  end
  return table.concat(out," ")
end
local function mprs()
  local state=emu.getState()
  local out={}
  for i=0,7 do
    out[#out+1]=string.format("%02X",
      assert(state["memoryManager.mpr["..i.."]"]))
  end
  return table.concat(out," ")
end
local function callback(addr,key)
  emu.addMemoryCallback(function()
    hits[key]=hits[key]+1
    if hits[key]<=4 then
      print(string.format(
        "SIDECAR_CALL f=%d hook=%s hits=%d mprs=[%s] code=[%s] portrait=[%s]",
        frame,key,hits[key],mprs(),hex(0x6000,8),hex(0x4CFA,12)
      ))
    end
  end,emu.callbackType.exec,addr,addr,CPU,MEM)
end
callback(0x80AF,"stub")
callback(0x6000,"sidecar")
callback(0x6038,"cache")
callback(0x8405,"portrait")
callback(0x4B20,"scan")
callback(0x5B95,"menu")
emu.addEventCallback(function()
  frame=frame+1
  if frame==3000 or frame==6000 or frame==8600 or frame==13300
    or frame==15600 or frame==16500 or frame==17760
    or frame==22500 or frame==24000 or frame==26000
    or frame==30000 or frame==34000 then
    print(string.format(
      "SIDECAR_CHECK f=%d pc=%04X mprs=[%s] stub=%d sidecar=%d cache=%d portrait=%d scan=%d menu=%d",
      frame,emu.getCpuState(CPU).pc,mprs(),hits.stub,hits.sidecar,
      hits.cache,hits.portrait,hits.scan,hits.menu
    ))
  end
  if frame==34000 then
    local success=hits.stub==3 and hits.sidecar==3 and
      hits.cache==3 and hits.portrait==2 and
      hits.scan==20 and hits.menu==3 and
      mprs()=="FF F8 80 81 82 83 84 00"
    print(string.format(
      "SIDECAR_RESULT success=%s stub=%d sidecar=%d cache=%d portrait=%d scan=%d menu=%d",
      tostring(success),hits.stub,hits.sidecar,hits.cache,
      hits.portrait,hits.scan,hits.menu
    ))
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
  elseif frame>=23000 and hits.stub<3 then
    -- Retry the approach after the extra optical seek shifts timing.
    local phase=(frame-23000)%1400
    if phase<110 then input.right=true
    elseif phase<800 then input.i=frame%40<7 end
  end
  emu.setInput(input,0)
end,emu.eventType.inputPolled)
