-- Reproduce the MesenCE 2.2.1 controlled *intro diagnostic* VWF proof.
-- Only applies to --authored-pixel-font --vwf-pilot
-- --diagnostic-intro-redirect on the source-guarded Mission 0 test disc.
-- This is a read-only CPU/bus trace, NOT a save-game patch.
-- Hook addresses must match the builder's m0b_pool_pilot_manifest.json
-- runtime_labels; do NOT reuse blindly with different runtime builds.
--
-- Launch:
--   Mesen --testRunner --enableStdout --timeout=150
--     --pcEngine.port1.type=PceController
--     tools/mesen_vwf_intro_trace.lua "/path/to/test-disc.cue"
--
-- The script intentionally does not use io/os, screenshots, or save files.
-- Reaching the VWF handler does NOT certify the bar or the entire game.

local mem=emu.memType.pceMemory
local cpu=emu.cpuType.pce
local frame=0
local redirects=0
local glyph_events=0
local display_cells=0
local vwf_disc_reads=0
local pool_disc_reads=0
local restorations=0

-- Full-disc BIOS LBAs; the four native $7C-$7F external-pool
-- reads are separated by four sectors each.
local VWF_LBA=44655
local POOL_FIRST_LBA=44639
local function r8(address) return emu.read(address,mem) end
local function zp(address) return r8(0x2000+address) end
local function observe(pc_address,callback)
  emu.addMemoryCallback(callback,emu.callbackType.exec,
    pc_address,pc_address,cpu,mem)
end

emu.addEventCallback(function()
  local v={}
  if frame>=90 and frame<195 then v.run=true end
  if frame>=700 and frame<735 then v.i=true end
  emu.setInput(v,0,0)
end,emu.eventType.inputPolled)

observe(0xB17A,function()
  if emu.getCpuState(cpu).a==0x7B then
    redirects=redirects+1
    print(string.format("VWF_INTRO_REDIRECT frame=%d",frame))
  end
end)

observe(0xB0A1,function()
  local hi=zp(0xF9)
  if redirects>0 and hi>=1 and hi<=9 then
    glyph_events=glyph_events+1
  end
end)

observe(0x5915,function()
  if redirects>0 and restorations==0 then
    display_cells=display_cells+1
    if display_cells<=12 then
      print(string.format("VWF_INTRO_CELL frame=%d count=%d",frame,display_cells))
    end
  end
end)

observe(0xB19F,function()
  if redirects>0 then
    restorations=restorations+1
    print(string.format("VWF_INTRO_SOURCE_RESTORED frame=%d",frame))
  end
end)

observe(0xE009,function()
  if redirects==0 then return end
  local lba=(zp(0xFC)<<16)|(zp(0xFD)<<8)|zp(0xFE)
  if lba>=POOL_FIRST_LBA and lba<=POOL_FIRST_LBA+12
     and (lba-POOL_FIRST_LBA)%4==0 then
    pool_disc_reads=pool_disc_reads+1
  end
  if lba==VWF_LBA then
    vwf_disc_reads=vwf_disc_reads+1
    print(string.format("VWF_INTRO_CARD_RAM_READ frame=%d lba=%d",frame,lba))
  end
end)

emu.addEventCallback(function()
  frame=frame+1
  if frame>=5850 then
    print(string.format(
      "VWF_INTRO_FINAL redirects=%d glyph_events=%d cells=%d "
      .."pool_reads=%d vwf_reads=%d restores=%d",
      redirects,glyph_events,display_cells,pool_disc_reads,
      vwf_disc_reads,restorations))
    emu.stop(0)
  end
end,emu.eventType.endFrame)
