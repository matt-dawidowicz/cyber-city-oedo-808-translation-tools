-- Reproducible MesenCE 2.2.1 *cold-boot* Mission 0 NPC benchmark.
-- No saved RAM, injected CPU state, patch code, or new game features.
-- Script delivers the same controller inputs to an authenticated original
-- disc and any separately derived test build; do not load a stock savestate
-- into a patched overlay for an A/B performance claim.
--
-- Run with Japanese System Card 3.0 BIOS, real PceController port 1:
-- Mesen --testRunner --enableStdout --timeout=180
--   --pcEngine.port1.type=PceController
--   tools/mesen_m0_npc_cold_ab.lua "/path/to/original-or-test.cue"
--
-- Source code identity/MPR should be confirmed independently for a new build.
-- Absolute frame schedules are sensitive to changed intro timing.
-- This measures the pre-bartender street NPC only, NOT the actual bar.

local frame=0
local press=10925
local parser_ready=nil
local reads=0
local adtrans=0
local fades=0
local mem=emu.memType.pceMemory
local cpu=emu.cpuType.pce

local function zp(a) return emu.read(0x2000+a,mem) end
local function watch(addr,fn)
  emu.addMemoryCallback(fn,emu.callbackType.exec,addr,addr,cpu,mem)
end

emu.addEventCallback(function()
  local v={}
  if frame>=90 and frame<195 then v.run=true end
  if frame>=700 and frame<735 then v.i=true end
  if frame>=10600 and frame<10720 then v.right=true end
  if frame>=10730 and frame<10850 then v.up=true end
  if frame>=10860 and frame<10916 then v.right=true end
  if frame>=press and frame<press+5 then v.i=true end
  emu.setInput(v,0,0)
end,emu.eventType.inputPolled)

watch(0xE02D,function()
  if frame>=press-250 then
    fades=fades+1
    print(string.format("NPC_AB_CD_FADE frame=%d",frame))
  end
end)

watch(0xE033,function()
  if frame>=press-250 then
    adtrans=adtrans+1
    print(string.format("NPC_AB_AD_TRANS frame=%d",frame))
  end
end)

watch(0xE009,function()
  if frame>=press-250 then
    reads=reads+1
    local lba=zp(0xFC)*65536+zp(0xFD)*256+zp(0xFE)
    if reads<=30 then
      print(string.format("NPC_AB_CD_READ frame=%d lba=%d",frame,lba))
    end
  end
end)

watch(0x9543,function()
  if frame>=press and parser_ready==nil then
    parser_ready=frame
    print(string.format(
      "NPC_AB_FIRST_PARSER frame=%d press=%d delta=%d",
      frame,press,frame-press))
  end
end)

emu.addEventCallback(function()
  frame=frame+1
  if frame==press then print("NPC_AB_INPUT_START frame="..press) end
  if frame>=12500 then
    print(string.format(
      "NPC_AB_FINAL first_parser=%s cd_reads=%d ad_trans=%d fades=%d",
      tostring(parser_ready),reads,adtrans,fades))
    emu.stop(0)
  end
end,emu.eventType.endFrame)
