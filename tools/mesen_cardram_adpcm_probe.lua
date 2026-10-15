-- Cyber City Oedo 808 - Super Card RAM ADPCM local-mode probe
-- Mesen 2.2.1 / PC Engine CD / System Card 3.0
--
-- CONTROLLED RUNTIME MUTATION. Disc image and System Card ROM are untouched.
--
-- Mission 0 normally maps physical CD-RAM bank $86 at logical $A000 and uses
-- AD_READ/AD_WRITE local-memory mode to snapshot 8 KiB of ADPCM RAM.
--
-- This probe changes only the three immediate "+6" bank-selection operands in
-- the loaded dialogue module to "+$FF". With the observed max_mapping=$80,
-- that maps Super Card RAM bank $7F at $A000 instead:
--
--     $80 + $FF = $7F (8-bit wrap)
--
-- Every AD_READ/AD_WRITE parameter and every surrounding game instruction is
-- otherwise stock. If local-memory mode follows the caller's MPR mapping, the
-- final 8 KiB of pceCardRam should receive the AD_READ snapshot and serve the
-- later AD_WRITE restore.
--
-- Run through a normal bartender/Mama dialogue, let control return, then stop
-- the script. A positive probe requires:
--   * System Card RAM size >= $30000;
--   * max_mapping $FFF5 == $80;
--   * at least one AD_READ and AD_WRITE entered with MPR5=$7F;
--   * Card RAM writes and reads in bank $7F;
--   * no source-guard failure.
--
-- This is a capability experiment, not a release patch.

local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory
local CARDRAM = emu.memType.pceCardRam

local frame = 0
local logFile = nil
local patched = false
local guardFailure = false
local adReadCalls = 0
local adWriteCalls = 0
local adReadIn7F = 0
local adWriteIn7F = 0
local card = {R=0,W=0,X=0,samples={}}

local PATCH_ADDRS = {0x839A, 0x83C6, 0x842C}
local STOCK_IMMEDIATE = 0x06
local PROBE_IMMEDIATE = 0xFF
local CARD_BANK = 0x7F
local CARD_BASE_BANK = 0x68
local CARD_OFFSET = (CARD_BANK - CARD_BASE_BANK) * 0x2000
local CARD_END = CARD_OFFSET + 0x1FFF

local function r8(address, memType)
  return emu.read(address, memType or MEM)
end

local function w8(address, value)
  emu.write(address, value, MEM)
end

local function cpu()
  return emu.getCpuState(CPU)
end

local function mprs()
  local state = emu.getState()
  local result = {}
  for i=0,7 do
    result[i] = state["memoryManager.mpr[" .. i .. "]"] or 0
  end
  return result
end

local function mprString()
  local m = mprs()
  local parts = {}
  for i=0,7 do
    parts[#parts+1] = string.format("MPR%d=$%02X", i, m[i])
  end
  return table.concat(parts, " ")
end

local function openLog()
  if type(io) ~= "table" or type(io.open) ~= "function" then return end
  local base = emu.getScriptDataFolder()
  if not base or base == "" then return end
  logFile = io.open(base .. "/cyber_oedo_cardram_adpcm_probe.log", "a")
  if logFile then
    logFile:write("\n=== NEW CARD-RAM ADPCM PROBE ===\n")
    logFile:flush()
  end
end

local function log(line)
  print(line)
  if logFile then
    logFile:write(line, "\n")
    logFile:flush()
  end
end

local function mission0ModuleMapped()
  local m = mprs()
  return m[4] == 0x85 and r8(0x8000) == 0x4C and r8(0x8003) == 0x4C
end

local function installProbe()
  if patched or guardFailure then return end
  if (emu.getMemorySize(CARDRAM) or 0) < 0x30000 then
    guardFailure = true
    log("[PROBE_ABORT] pceCardRam is smaller than 192 KiB")
    return
  end
  if r8(0xFFF5) ~= 0x80 then
    guardFailure = true
    log(string.format("[PROBE_ABORT] max_mapping=$%02X expected $80", r8(0xFFF5)))
    return
  end
  if not mission0ModuleMapped() then
    return
  end
  for _,address in ipairs(PATCH_ADDRS) do
    if r8(address) ~= STOCK_IMMEDIATE then
      guardFailure = true
      log(string.format(
        "[PROBE_ABORT] source guard $%04X=$%02X expected $06",
        address, r8(address)
      ))
      return
    end
  end
  for _,address in ipairs(PATCH_ADDRS) do
    w8(address, PROBE_IMMEDIATE)
  end
  patched = true
  log(string.format(
    "[PROBE_INSTALLED] frame=%d max_mapping=$%02X target_bank=$%02X %s",
    frame, r8(0xFFF5), CARD_BANK, mprString()
  ))
end

local function restoreProbe()
  if not patched then return end
  if mission0ModuleMapped() then
    for _,address in ipairs(PATCH_ADDRS) do
      if r8(address) == PROBE_IMMEDIATE then
        w8(address, STOCK_IMMEDIATE)
      end
    end
  end
  patched = false
end

local function sampleCard(kind, address, value)
  card[kind] = card[kind] + 1
  if #card.samples < 32 then
    card.samples[#card.samples+1] = string.format(
      "%s off=$%05X value=$%02X frame=%d PC=$%04X",
      kind, address, value or 0, frame, cpu().pc or 0
    )
  end
end

local function onAdRead()
  adReadCalls = adReadCalls + 1
  local m = mprs()
  if m[5] == CARD_BANK then adReadIn7F = adReadIn7F + 1 end
  log(string.format(
    "[AD_READ %d] frame=%d adpcm=$%04X mem=$%04X bytes=$%04X type=$%02X %s",
    adReadCalls, frame, emu.read16(0x20FC,MEM,false),
    emu.read16(0x20FA,MEM,false), emu.read16(0x20F8,MEM,false),
    r8(0x20FF), mprString()
  ))
end

local function onAdWrite()
  adWriteCalls = adWriteCalls + 1
  local m = mprs()
  if m[5] == CARD_BANK then adWriteIn7F = adWriteIn7F + 1 end
  log(string.format(
    "[AD_WRITE %d] frame=%d adpcm=$%04X mem=$%04X bytes=$%04X type=$%02X %s",
    adWriteCalls, frame, emu.read16(0x20FC,MEM,false),
    emu.read16(0x20FA,MEM,false), emu.read16(0x20F8,MEM,false),
    r8(0x20FF), mprString()
  ))
end

openLog()
log("Cyber City Oedo 808 Card-RAM ADPCM probe armed.")
log("Controlled runtime mutation: YES; disc/System Card mutation: NO")

-- $48CD is the stock return after the Mission 0 dialogue module byte-loader.
emu.addMemoryCallback(installProbe, emu.callbackType.exec, 0x48CD, 0x48CD, CPU, MEM)
-- Also try at the loader probe so cache-hit/re-entry coverage can reinstall.
emu.addMemoryCallback(installProbe, emu.callbackType.exec, 0x48A6, 0x48A6, CPU, MEM)
emu.addMemoryCallback(onAdRead, emu.callbackType.exec, 0xE036, 0xE036, CPU, MEM)
emu.addMemoryCallback(onAdWrite, emu.callbackType.exec, 0xE039, 0xE039, CPU, MEM)

emu.addMemoryCallback(
  function(a,v) sampleCard("R",a,v) end,
  emu.callbackType.read, CARD_OFFSET, CARD_END, CPU, CARDRAM
)
emu.addMemoryCallback(
  function(a,v) sampleCard("W",a,v) end,
  emu.callbackType.write, CARD_OFFSET, CARD_END, CPU, CARDRAM
)
emu.addMemoryCallback(
  function(a,v) sampleCard("X",a,v) end,
  emu.callbackType.exec, CARD_OFFSET, CARD_END, CPU, CARDRAM
)

emu.addEventCallback(function()
  frame = frame + 1
  if patched and frame % 600 == 0 then
    log(string.format(
      "[HEARTBEAT] frame=%d AD_READ=%d(%d in $7F) AD_WRITE=%d(%d in $7F) " ..
      "card_R/W/X=%d/%d/%d %s",
      frame, adReadCalls, adReadIn7F, adWriteCalls, adWriteIn7F,
      card.R, card.W, card.X, mprString()
    ))
  end
end, emu.eventType.endFrame)

emu.addEventCallback(function()
  restoreProbe()
  log(string.format(
    "[SUMMARY] frames=%d guard_failure=%s AD_READ=%d in7F=%d " ..
    "AD_WRITE=%d in7F=%d card_R/W/X=%d/%d/%d",
    frame, tostring(guardFailure), adReadCalls, adReadIn7F,
    adWriteCalls, adWriteIn7F, card.R, card.W, card.X
  ))
  for index,sample in ipairs(card.samples) do
    log(string.format("[CARD_SAMPLE %02d] %s", index, sample))
  end
  if not guardFailure
     and adReadIn7F > 0
     and adWriteIn7F > 0
     and card.W > 0
     and card.R > 0
     and card.X == 0 then
    log("RESULT: Card RAM local-mode ADPCM snapshot path observed successfully.")
    log("Promotion still requires audible/state-correct playtest and repeat coverage.")
  else
    log("RESULT: Card RAM ADPCM capability gate NOT closed by this session.")
  end
  if logFile then
    logFile:flush()
    logFile:close()
    logFile = nil
  end
end, emu.eventType.scriptEnded)
