-- Cyber City Oedo 808 - B3 bank $87 residency lifecycle probe V6
-- Mesen 2.2.1 / PC Engine CD / stock Japanese System Card 3.0
--
-- Controlled runtime mutation only. This script does NOT modify the disc image or System Card.
-- It waits for the game's natural H_BARTEN byte-loader call, lets that stock load finish,
-- then temporarily uses the game's own $6EA0 loader to read one authenticated data sector
-- (absolute disc LBA $0010DD) into $A000 while MPR5 maps physical CD-RAM bank $87.
-- All displaced game bytes, loader scratch bytes, MPR5, direct-page parameters and BIOS
-- argument registers are restored before normal execution resumes.
--
-- Persistent log: cyber_oedo_bank87_residency_v6.log
-- Enable Script Window -> Settings -> Allow I/O and OS access.

local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory
local CDRAM = emu.memType.pceCdromRam

local TRACK2_START_LBA = 3590
local TRACK2_END_LBA_EXCLUSIVE = 44789
local TEST_ABS_LBA = 0x0010DD
local TEST_TRACK2_REL = TEST_ABS_LBA - TRACK2_START_LBA
local TEST_PAYLOAD_OFF = TEST_TRACK2_REL * 0x800
local TEST_LEN = 0x0800
local TEST_SHA256 = "054603d9b31b5d1c4bff6cec3d683c151bf88295f2b312684ebfde0bac3f114a"
local EXPECTED_NONZERO = {{0x000,0x48},{0x001,0x5F},{0x002,0x42},{0x003,0x41},{0x004,0x52},{0x005,0x54},{0x006,0x45},{0x007,0x4E},{0x00A,0x70},{0x010,0xFF},{0x011,0xFE},{0x013,0xFF},{0x014,0xFE},{0x016,0x0B},{0x01D,0x04},{0x020,0x33},{0x021,0x03},{0x023,0x3D},{0x024,0x34},{0x025,0x03},{0x027,0x03},{0x028,0x06},{0x02B,0x03},{0x02D,0x19},{0x02E,0x26},{0x02F,0x48},{0x030,0x03},{0x032,0x01},{0x033,0x03},{0x035,0x02},{0x036,0x03},{0x038,0x01},{0x039,0x48},{0x03A,0x03},{0x03C,0x01},{0x03D,0x03},{0x03F,0x01},{0x040,0x27},{0x041,0x28},{0x042,0x83},{0x043,0x6F},{0x044,0x81},{0x045,0x5B},{0x046,0x83},{0x047,0x65},{0x048,0x83},{0x049,0x93},{0x04A,0x81},{0x04B,0x75},{0x04C,0x82},{0x04D,0xA2},{0x04E,0x82},{0x04F,0xE7},{0x050,0x82},{0x051,0xC1},{0x052,0x82},{0x053,0xB5},{0x054,0x82},{0x055,0xE1},{0x056,0x82},{0x057,0xA2},{0x058,0x82},{0x059,0xDC},{0x05A,0x82},{0x05B,0xB9},{0x05C,0x81},{0x05D,0x76},{0x05F,0x48},{0x060,0x03},{0x062,0x01},{0x063,0x03},{0x066,0x49},{0x067,0x03},{0x069,0xFF},{0x06A,0x03},{0x06D,0x03},{0x070,0x03}}
local STUB_HEX = [[08488a489848a50048a50148a50248a50348a50448a50548a50648a50748a5f848a5f948a5fa48a5fb48a5fc48a5fd48a5fe48a5ff48432048a9875320a9008500a9a08501a9008502a9dd8504a9108505a9008506a908850720a06e6853206885ff6885fe6885fd6885fc6885fb6885fa6885f96885f868850768850668850568850468850368850268850168850068a868aa6828adc76c4c826d]]

local function decode_hex(s)
  local t = {}
  for i=1,#s,2 do t[#t+1] = tonumber(s:sub(i,i+1),16) end
  return t
end
local expected = {}
for i=1,TEST_LEN do expected[i]=0 end
for _,p in ipairs(EXPECTED_NONZERO) do expected[p[1]+1]=p[2] end
local stub = decode_hex(STUB_HEX)

local frame = 0
local ended = false
local logFile = nil
local logPath = nil
local naturalHBartenActive = false
local trampolineInstalled = false
local injectionComplete = false
local injectionFailed = false
local testLoaderSeen = false
local testCdReadSeen = false
local originalTarget = {}
local originalScratch = {}
local integrityChecks = 0
local integrityFailures = 0
local firstIntegrityFailure = nil
local postInjection87 = {R=0,W=0,X=0,samples={}}
local total87 = {R=0,W=0,X=0}
local total85 = {R=0,W=0,X=0}
local hBartenReads = 0
local parserHits = 0
local rendererHits = 0
local dialogueGroups = 0
local lastParserFrame = -100000
local cdReads = 0
local cdBursts = 0
local lastCdFrame = -100000
local lastMprs = nil

local function open_log()
  if type(io) ~= "table" or type(io.open) ~= "function" then return false end
  local base = emu.getScriptDataFolder()
  if not base or base == "" then return false end
  logPath = base .. "/cyber_oedo_bank87_residency_v6.log"
  local f = io.open(logPath,"a")
  if not f then return false end
  logFile = f
  logFile:write("\n\n================ V6 NEW RESIDENCY SESSION ================\n")
  logFile:flush()
  return true
end
local function log(s)
  s=tostring(s or "")
  print(s)
  if logFile then logFile:write(s,"\n"); logFile:flush() end
end
local function banner(s)
  log(""); log("================================================================"); log(s); log("================================================================")
end
local function r8(a,mt) return emu.read(a,mt or MEM) end
local function r16(a) return emu.read16(a,MEM,false) end
local function w8(a,v,mt) emu.write(a,v,mt or MEM) end
local function cpu() return emu.getCpuState(CPU) end
local function get_mprs()
  local s=emu.getState(); local t={}
  for i=0,7 do t[i]=s["memoryManager.mpr["..i.."]"] or 0 end
  return t
end
local function mpr_string(m)
  m=m or get_mprs(); local t={}
  for i=0,7 do t[#t+1]=string.format("MPR%d=$%02X",i,m[i]) end
  return table.concat(t," ")
end
local function stack_return_target()
  local c=cpu(); local sp=c.sp
  local lo=r8(0x2100+((sp+1)&0xFF)); local hi=r8(0x2100+((sp+2)&0xFF))
  return ((((hi<<8)|lo)+1)&0xFFFF)
end
local function loader_tuple()
  local dest=r16(0x2000)
  local lba=(r8(0x2002)<<16)|(r8(0x2005)<<8)|r8(0x2004)
  local len=r16(0x2006)
  return dest,lba,len
end
local function track2_coords(absLba)
  if absLba < TRACK2_START_LBA or absLba >= TRACK2_END_LBA_EXCLUSIVE then return nil,nil end
  local rel=absLba-TRACK2_START_LBA
  return rel,rel*0x800
end
local function compare_payload()
  local bad=0; local first=-1
  for i=0,#expected-1 do
    local v=r8(0xE000+i,CDRAM)
    if v~=expected[i+1] then bad=bad+1; if first<0 then first=i end end
  end
  return bad,first
end
local function check_integrity(reason)
  if not injectionComplete then return end
  integrityChecks=integrityChecks+1
  local bad,first=compare_payload()
  log(string.format("[INTEGRITY %03d] frame=%d reason=%s mismatches=%d first=%d",integrityChecks,frame,reason,bad,first))
  if bad~=0 then
    integrityFailures=integrityFailures+1
    if not firstIntegrityFailure then firstIntegrityFailure={frame=frame,offset=first,bad=bad} end
    emu.displayMessage("Cyber Oedo V6",string.format("BANK $87 PAYLOAD CHANGED: %d mismatches",bad))
  end
end
local function install_trampoline()
  if trampolineInstalled or injectionComplete then return end
  local stock={0xAD,0xC7,0x6C}
  for i=0,2 do
    originalTarget[i]=r8(0x6D7F+i)
    if originalTarget[i]~=stock[i+1] then
      injectionFailed=true
      log(string.format("ERROR: $6D7F stock guard failed at +%d: got $%02X expected $%02X",i,originalTarget[i],stock[i+1]))
      emu.displayMessage("Cyber Oedo V6","Injection aborted: $6D7F guard mismatch")
      return
    end
  end
  for i=0,#stub-1 do originalScratch[i]=r8(0x29D0+i) end
  for i=0,#stub-1 do w8(0x29D0+i,stub[i+1]) end
  w8(0x6D7F,0x20); w8(0x6D80,0xD0); w8(0x6D81,0x29) -- JSR $29D0
  trampolineInstalled=true
  banner("V6 TEMPORARY TRAMPOLINE INSTALLED AFTER STOCK H_BARTEN LOAD")
  log(string.format("frame=%d stock $6D7F bytes=%02X %02X %02X scratch=$29D0 length=%d",frame,originalTarget[0],originalTarget[1],originalTarget[2],#stub))
end
local function restore_trampoline_and_verify()
  if not trampolineInstalled or injectionComplete then return end
  for i=0,2 do w8(0x6D7F+i,originalTarget[i]) end
  for i=0,#stub-1 do w8(0x29D0+i,originalScratch[i]) end
  trampolineInstalled=false
  injectionComplete=true
  local m=get_mprs(); local bad,first=compare_payload()
  banner("V6 $87 LOADER/RESIDENCY INJECTION COMPLETE")
  log(string.format("frame=%d MPR5=$%02X expected restored=$83",frame,m[5]))
  log(string.format("payload exact-byte comparison: mismatches=%d first=%d",bad,first))
  log("authenticated source SHA-256: "..TEST_SHA256)
  log(string.format("source absolute LBA=$%06X Track2-relative=$%04X payload-offset=$%08X length=$%04X",TEST_ABS_LBA,TEST_TRACK2_REL,TEST_PAYLOAD_OFF,TEST_LEN))
  if m[5]~=0x83 or bad~=0 or not testLoaderSeen or not testCdReadSeen then
    injectionFailed=true
    log("ERROR: controlled injection did not satisfy all immediate verification gates")
    emu.displayMessage("Cyber Oedo V6","$87 injection verification FAILED - see log")
  else
    emu.displayMessage("Cyber Oedo V6","$87 payload loaded and verified - continue lifecycle test")
  end
end

local addressTypeNames={[0x00]="LOCAL_BYTES",[0x01]="LOCAL_SECTORS",[0x02]="BANK_MPR2",[0x03]="BANK_MPR3",[0x04]="BANK_MPR4",[0x05]="BANK_MPR5",[0x06]="BANK_MPR6",[0xFE]="VRAM_BYTES",[0xFF]="VRAM_SECTORS"}

local function on_loader()
  local dest,lba,len=loader_tuple(); local ret=stack_return_target()
  if not injectionComplete and not trampolineInstalled and not injectionFailed and dest==0xC660 and lba==TEST_ABS_LBA and len==0x0080 and ret==0x6D7F then
    naturalHBartenActive=true
    banner("NATURAL H_BARTEN BYTE-LOADER CALL OBSERVED")
    log(string.format("frame=%d dest=$%04X absLBA=$%06X len=$%04X return=$%04X %s",frame,dest,lba,len,ret,mpr_string()))
  elseif trampolineInstalled and dest==0xA000 and lba==TEST_ABS_LBA and len==TEST_LEN then
    testLoaderSeen=true
    banner("CONTROLLED $87 TEST BYTE-LOADER CALL")
    log(string.format("frame=%d dest=$%04X absLBA=$%06X len=$%04X return=$%04X %s",frame,dest,lba,len,ret,mpr_string()))
  end
end
local function on_loader_rts()
  if naturalHBartenActive and not trampolineInstalled and not injectionComplete and not injectionFailed then
    naturalHBartenActive=false
    install_trampoline()
  end
end
local function on_cdread()
  cdReads=cdReads+1
  if frame-lastCdFrame>90 then cdBursts=cdBursts+1; banner(string.format("CD LOAD BURST %d START frame=%d",cdBursts,frame)) end
  lastCdFrame=frame
  local len=r16(0x20F8); local dest=r16(0x20FA)
  local lba=(r8(0x20FC)<<16)|(r8(0x20FD)<<8)|r8(0x20FE); local typ=r8(0x20FF)
  local rel,off=track2_coords(lba); local unit=(typ==0x00 or typ==0xFE) and "bytes" or "sectors"
  local coords=rel and string.format("track2_rel=$%04X payload_off=$%08X",rel,off) or "outside_track2"
  log(string.format("[CD_READ %03d B%02d] frame=%d absLBA=$%06X %s type=$%02X(%s) dest=$%04X len=$%04X_%s %s",cdReads,cdBursts,frame,lba,coords,typ,addressTypeNames[typ] or "UNKNOWN",dest,len,unit,mpr_string()))
  if trampolineInstalled and lba==TEST_ABS_LBA and dest==0xA000 and len==1 and typ==1 and get_mprs()[5]==0x87 then
    testCdReadSeen=true
    log("*** VERIFIED TEST CD_READ: direct one-sector BIOS transfer while MPR5=$87 ***")
  end
end

local function bank_event(bank,kind,a,v)
  local target=(bank==0x85) and total85 or total87
  target[kind]=target[kind]+1
  if bank==0x87 and injectionComplete then
    postInjection87[kind]=postInjection87[kind]+1
    if #postInjection87.samples<40 then
      local c=cpu(); local s=string.format("%s callback=$%04X value=$%02X PC=$%04X frame=%d",kind,a,v or 0,c.pc or 0,frame)
      postInjection87.samples[#postInjection87.samples+1]=s
      log("[POST-INJECTION BANK $87] "..s)
    end
  end
end
local function register_bank(bank)
  local start=(bank-0x80)*0x2000; local stop=start+0x1FFF
  emu.addMemoryCallback(function(a,v) bank_event(bank,"R",a,v) end,emu.callbackType.read,start,stop,CPU,CDRAM)
  emu.addMemoryCallback(function(a,v) bank_event(bank,"W",a,v) end,emu.callbackType.write,start,stop,CPU,CDRAM)
  emu.addMemoryCallback(function(a,v) bank_event(bank,"X",a,v) end,emu.callbackType.exec,start,stop,CPU,CDRAM)
end
local function parser_hit()
  parserHits=parserHits+1
  if frame-lastParserFrame>300 then dialogueGroups=dialogueGroups+1; banner(string.format("DIALOGUE GROUP %d START frame=%d",dialogueGroups,frame)) end
  lastParserFrame=frame
  local ptr=r16(0x207F); local b0=r8(ptr); local b1=r8((ptr+1)&0xFFFF)
  if b0<0x80 or ptr==0xC692 then log(string.format("[PARSER %03d G%02d] frame=%d ptr=$%04X bytes=%02X %02X",parserHits,dialogueGroups,frame,ptr,b0,b1)) end
end
local function renderer_hit() rendererHits=rendererHits+1 end
local function h_barten_read() hBartenReads=hBartenReads+1 end
local function monitor_mprs()
  local m=get_mprs(); local changed=false
  if not lastMprs then changed=true else for i=0,7 do if m[i]~=lastMprs[i] then changed=true break end end end
  if changed then
    local interesting=false
    for i=0,7 do if m[i]==0x87 or (lastMprs and lastMprs[i]==0x87) then interesting=true end end
    if interesting then log(string.format("[MPR $87 CHANGE] frame=%d %s",frame,mpr_string(m))) end
    lastMprs=m
  end
end
local function cleanup_transient()
  if trampolineInstalled and not injectionComplete then
    for i=0,2 do if originalTarget[i] then w8(0x6D7F+i,originalTarget[i]) end end
    for i=0,#stub-1 do if originalScratch[i] then w8(0x29D0+i,originalScratch[i]) end end
    trampolineInstalled=false
    log("Transient trampoline bytes restored during script shutdown")
  end
end
local function summary(reason)
  if ended then return end; ended=true
  cleanup_transient()
  banner("V6 FINAL SUMMARY - "..reason)
  log(string.format("frames=%d injectionComplete=%s injectionFailed=%s testLoaderSeen=%s testCdReadSeen=%s",frame,tostring(injectionComplete),tostring(injectionFailed),tostring(testLoaderSeen),tostring(testCdReadSeen)))
  log(string.format("dialogue_groups=%d parser_hits=%d renderer_hits=%d H_BARTEN_reads=%d CD_READs=%d CD_bursts=%d",dialogueGroups,parserHits,rendererHits,hBartenReads,cdReads,cdBursts))
  log(string.format("BANK $85 total CPU physical activity: R=%d W=%d X=%d",total85.R,total85.W,total85.X))
  log(string.format("BANK $87 total CPU physical activity: R=%d W=%d X=%d",total87.R,total87.W,total87.X))
  log(string.format("BANK $87 POST-INJECTION CPU activity: R=%d W=%d X=%d",postInjection87.R,postInjection87.W,postInjection87.X))
  log(string.format("payload integrity checks=%d failures=%d",integrityChecks,integrityFailures))
  if firstIntegrityFailure then log(string.format("first payload failure: frame=%d offset=$%04X mismatches=%d",firstIntegrityFailure.frame,firstIntegrityFailure.offset,firstIntegrityFailure.bad)) end
  if injectionComplete then
    local bad,first=compare_payload(); log(string.format("FINAL payload comparison: mismatches=%d first=%d SHA-if-exact=%s",bad,first,bad==0 and TEST_SHA256 or "NOT-EXACT"))
  end
  for i,s in ipairs(postInjection87.samples) do log(string.format("  $87 sample %02d: %s",i,s)) end
  if injectionComplete and not injectionFailed and integrityFailures==0 and postInjection87.W==0 and postInjection87.X==0 then
    log("RESULT: controlled $87 payload remained intact with no post-injection stock writes/executes during this capture window.")
    log("Promotion still depends on the operator having completed the requested bartender + menu + exit/re-entry lifecycle.")
  else
    log("RESULT: $87 residency gate NOT closed by this session; inspect failure/activity lines above.")
  end
  if logFile then logFile:flush(); logFile:close(); logFile=nil end
end

local ioOk=open_log()
banner("CYBER CITY OEDO 808 - B3 BANK $87 RESIDENCY LIFECYCLE PROBE V6")
log("Persistent log: "..tostring(logPath or "DISABLED"))
log("Controlled runtime mutation: YES; disc mutation: NO; System Card mutation: NO")
log(string.format("Authenticated source: absolute LBA=$%06X Track2-relative=$%04X payload-offset=$%08X length=$%04X SHA-256=%s",TEST_ABS_LBA,TEST_TRACK2_REL,TEST_PAYLOAD_OFF,TEST_LEN,TEST_SHA256))
log("Injection trigger: first natural H_BARTEN $6EA0 load (dest $C660, length $0080, return $6D7F)")
log("After injection: perform bartender, menu/choice NPC(s), leave bar, re-enter bar, and interact again before stopping script.")
if not ioOk then log("ERROR: enable Script Window -> Settings -> Allow I/O and OS access, then reload V6") end

emu.addMemoryCallback(on_loader,emu.callbackType.exec,0x6EA0,0x6EA0,CPU,MEM)
emu.addMemoryCallback(on_loader_rts,emu.callbackType.exec,0x6EED,0x6EED,CPU,MEM)
emu.addMemoryCallback(on_cdread,emu.callbackType.exec,0xE009,0xE009,CPU,MEM)
emu.addMemoryCallback(function() if trampolineInstalled and testLoaderSeen and not injectionComplete then restore_trampoline_and_verify() end end,emu.callbackType.exec,0x6D82,0x6D82,CPU,MEM)
emu.addMemoryCallback(parser_hit,emu.callbackType.exec,0x9543,0x9543,CPU,MEM)
emu.addMemoryCallback(renderer_hit,emu.callbackType.exec,0x5915,0x5915,CPU,MEM)
emu.addMemoryCallback(h_barten_read,emu.callbackType.read,0xC692,0xC692,CPU,MEM)
register_bank(0x85); register_bank(0x87)

emu.addEventCallback(function()
  frame=frame+1; monitor_mprs()
  if injectionComplete and frame%300==0 then check_integrity("periodic") end
  if frame%600==0 then
    local bad=-1
    if injectionComplete then bad=select(1,compare_payload()) end
    log(string.format("[HEARTBEAT] frame=%d injected=%s payload_mismatches=%d $85=%d/%d/%d $87total=%d/%d/%d $87post=%d/%d/%d",frame,tostring(injectionComplete),bad,total85.R,total85.W,total85.X,total87.R,total87.W,total87.X,postInjection87.R,postInjection87.W,postInjection87.X))
    emu.displayMessage("Cyber Oedo V6",injectionComplete and string.format("$87 resident: mismatches=%d postW=%d",bad,postInjection87.W) or "Armed - talk to bartender to trigger $87 load")
  end
end,emu.eventType.endFrame)
emu.addEventCallback(function() summary("script ended") end,emu.eventType.scriptEnded)

emu.displayMessage("Cyber Oedo V6","V6 armed - talk to bartender; then run menu + exit/re-entry coverage")
