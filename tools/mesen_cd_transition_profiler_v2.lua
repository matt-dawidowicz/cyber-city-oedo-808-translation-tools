-- Cyber City Oedo 808 - CD transition profiler v2
-- Mesen 2.2.1 / PC Engine CD
--
-- READ ONLY.  This version measures every System Card CD_READ from BIOS entry
-- to its exact caller return target, instead of timing only the two known scene
-- wrappers. It also records CD_EXEC overlay loads to their first target
-- instruction, CD_PLAY/CD_PAUSE mode switches, generic byte-loader calls, and
-- AD_TRANS transfers, exact AD_READ/AD_WRITE memory-transfer timing,
-- records ADPCM stop/status/fade activity, counts EX_VSYNC calls, and records
-- when dialogue parsing becomes active again.
--
-- Recommended coverage:
--   * enter/leave the bar several times;
--   * trigger bartender/Mama/other portrait dialogue;
--   * enter at least one alternate room and return;
--   * stop the script only after normal control has resumed.
--
-- Persistent log: cyber_oedo_cd_transition_profile_v2.log
--
-- Additional transition timing markers:
--   $80E7  dialogue-module fade command
--   $8100  dialogue-module audio-state clear path
--   $41EC  outer synchronous fade-wait loop
--   $41F1  first instruction after the fade-wait loop
-- MPRs are logged at all logical hooks to prevent overlay-address confusion.
-- pceCardRam is monitored separately from the 64 KiB CD-ROM unit RAM so the
-- System Card 3.0 expansion can be evaluated as a cache target.

local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory
local CDRAM = emu.memType.pceCdromRam
local CARDRAM = emu.memType.pceCardRam

local TRACK2_START_LBA = 3590
local frame = 0
local readOrdinal = 0
local cdExecOrdinal = 0
local cdPlayCalls = 0
local cdPauseCalls = 0
local byteLoaderOrdinal = 0
local dialogueGroups = 0
local parserHits = 0
local adTransOrdinal = 0
local adReadOrdinal = 0
local adWriteOrdinal = 0
local adStopCalls = 0
local adStatCalls = 0
local cdFadeCalls = 0
local vsyncCalls = 0
local lastParserFrame = -100000
local lastCdFrame = -100000
local logFile = nil

local pendingReadsByReturn = {}
local registeredReturnTargets = {}
local pendingExecByTarget = {}
local registeredExecTargets = {}
local pendingByteLoader = nil
local pendingAdTransByReturn = {}
local registeredAdTransReturns = {}
local pendingAdMemoryByReturn = {}
local registeredAdMemoryReturns = {}
local fadeCommandStartFrame = nil
local fadeWaitStartFrame = nil
local fadeWaitSamples = 0
local cardRam = {size=0,R=0,W=0,X=0,samples={}}
local transitionWindow = nil

local function addTransitionFrames(kind, frames)
  if not transitionWindow then return end
  transitionWindow.frames[kind] = transitionWindow.frames[kind] + frames
  transitionWindow.counts[kind] = transitionWindow.counts[kind] + 1
end

local function r8(address, memType)
  return emu.read(address, memType or MEM)
end

local function r16(address)
  return emu.read16(address, MEM, false)
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

local function mprString(values)
  values = values or mprs()
  local out = {}
  for i=0,7 do
    out[#out+1] = string.format("MPR%d=$%02X", i, values[i])
  end
  return table.concat(out, " ")
end

local function stackReturnTarget()
  local state = cpu()
  local sp = state.sp or 0
  local lo = r8(0x2100 + ((sp + 1) & 0xFF))
  local hi = r8(0x2100 + ((sp + 2) & 0xFF))
  return ((((hi << 8) | lo) + 1) & 0xFFFF)
end

local function openLog()
  if type(io) ~= "table" or type(io.open) ~= "function" then return end
  local base = emu.getScriptDataFolder()
  if not base or base == "" then return end
  logFile = io.open(base .. "/cyber_oedo_cd_transition_profile_v2.log", "a")
  if logFile then
    logFile:write("\n=== NEW CD TRANSITION PROFILE V2 SESSION ===\n")
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

local function onCardRam(kind, address, value)
  cardRam[kind] = cardRam[kind] + 1
  if #cardRam.samples < 32 then
    local state = cpu()
    cardRam.samples[#cardRam.samples + 1] = string.format(
      "%s addr=$%05X value=$%02X PC=$%04X frame=%d",
      kind, address, value or 0, state.pc or 0, frame
    )
  end
end

local function armCardRamMonitor()
  cardRam.size = emu.getMemorySize(CARDRAM) or 0
  log(string.format("[CARD_RAM] size=%d bytes ($%X)", cardRam.size, cardRam.size))
  if cardRam.size <= 0 then return end
  local last = cardRam.size - 1
  emu.addMemoryCallback(
    function(a,v) onCardRam("R", a, v) end,
    emu.callbackType.read, 0, last, CPU, CARDRAM
  )
  emu.addMemoryCallback(
    function(a,v) onCardRam("W", a, v) end,
    emu.callbackType.write, 0, last, CPU, CARDRAM
  )
  emu.addMemoryCallback(
    function(a,v) onCardRam("X", a, v) end,
    emu.callbackType.exec, 0, last, CPU, CARDRAM
  )
end

local function sceneState()
  return string.format(
    "scene=$%02X room=$%02X resume=$%02X",
    r8(0x3700), r8(0x3701), r8(0x3702)
  )
end

local addressTypeNames = {
  [0x00]="UNDOCUMENTED_00",
  [0x01]="LOCAL_SECTORS",
  [0x02]="BANK_MPR2",
  [0x03]="BANK_MPR3",
  [0x04]="BANK_MPR4",
  [0x05]="BANK_MPR5",
  [0x06]="BANK_MPR6",
  [0xFE]="VRAM_BYTES",
  [0xFF]="VRAM_SECTORS",
}

local function ensureReturnCallback(target)
  if registeredReturnTargets[target] then return end
  registeredReturnTargets[target] = true

  emu.addMemoryCallback(
    function()
      local queue = pendingReadsByReturn[target]
      if not queue or #queue == 0 then return end

      local item = table.remove(queue, 1)
      local elapsed = frame - item.startFrame
      addTransitionFrames("cd_read", elapsed)
      local c = cpu()
      log(string.format(
        "[CD_READ_RETURN %03d] frame=%d elapsed_frames=%d elapsed_seconds=%.4f " ..
        "sector=$%06X type=$%02X dest=$%04X len=$%04X_%s return=$%04X " ..
        "A=$%02X X=$%02X %s %s",
        item.ordinal, frame, elapsed, elapsed / 60.0,
        item.sector, item.addressType, item.destination, item.length, item.unit,
        target, c.a or 0, c.x or 0, sceneState(), mprString()
      ))
    end,
    emu.callbackType.exec,
    target, target, CPU, MEM
  )
end

local function ensureExecTargetCallback(target)
  if registeredExecTargets[target] then return end
  registeredExecTargets[target] = true
  emu.addMemoryCallback(
    function()
      local queue = pendingExecByTarget[target]
      if not queue or #queue == 0 then return end
      local item = table.remove(queue, 1)
      local elapsed = frame - item.startFrame
      addTransitionFrames("cd_exec", elapsed)
      log(string.format(
        "[CD_EXEC_TARGET %03d] frame=%d elapsed_frames=%d elapsed_seconds=%.4f " ..
        "sector=$%06X blocks=$%02X target=$%04X %s %s",
        item.ordinal, frame, elapsed, elapsed / 60.0,
        item.sector, item.blocks, target, sceneState(), mprString()
      ))
    end,
    emu.callbackType.exec,
    target, target, CPU, MEM
  )
end

local function onCdExec()
  cdExecOrdinal = cdExecOrdinal + 1
  local addressType = r8(0x20FF)
  local item = {
    ordinal=cdExecOrdinal,
    startFrame=frame,
    sector=(r8(0x20FC) << 16) | (r8(0x20FD) << 8) | r8(0x20FE),
    blocks=r8(0x20F8),
    addressType=addressType,
    bx=r16(0x20FA),
  }

  -- In documented LOCAL mode ($01), BX is the destination/execute address.
  -- In MPR modes ($02-$06), BL is a bank number; BX must not be interpreted
  -- as a logical PC target without additional runtime proof.
  if addressType == 0x01 then
    item.target = item.bx
    if not pendingExecByTarget[item.target] then
      pendingExecByTarget[item.target] = {}
    end
    table.insert(pendingExecByTarget[item.target], item)
    ensureExecTargetCallback(item.target)
  end

  log(string.format(
    "[CD_EXEC %03d] frame=%d sector=$%06X blocks=$%02X type=$%02X " ..
    "bx=$%04X local_target=%s %s %s",
    item.ordinal, frame, item.sector, item.blocks, item.addressType, item.bx,
    item.target and string.format("$%04X", item.target) or "unproven",
    sceneState(), mprString()
  ))
end

local function onCdPlay()
  cdPlayCalls = cdPlayCalls + 1
  log(string.format(
    "[CD_PLAY %03d] frame=%d mode=$%02X return=$%04X %s %s",
    cdPlayCalls, frame, r8(0x20FF), stackReturnTarget(), sceneState(), mprString()
  ))
end

local function onCdPause()
  cdPauseCalls = cdPauseCalls + 1
  log(string.format(
    "[CD_PAUSE %03d] frame=%d return=$%04X %s %s",
    cdPauseCalls, frame, stackReturnTarget(), sceneState(), mprString()
  ))
end

local function ensureAdMemoryReturnCallback(target)
  if registeredAdMemoryReturns[target] then return end
  registeredAdMemoryReturns[target] = true
  emu.addMemoryCallback(
    function()
      local queue = pendingAdMemoryByReturn[target]
      if not queue or #queue == 0 then return end
      local item = table.remove(queue, 1)
      local elapsed = frame - item.startFrame
      addTransitionFrames(item.kind == "AD_READ" and "ad_read" or "ad_write", elapsed)
      local state = cpu()
      log(string.format(
        "[%s_RETURN %03d] frame=%d elapsed_frames=%d elapsed_seconds=%.4f " ..
        "adpcm=$%04X mem=$%04X bytes=$%04X type=$%02X return=$%04X " ..
        "A=$%02X X=$%02X %s %s",
        item.kind, item.ordinal, frame, elapsed, elapsed / 60.0,
        item.adpcm, item.memory, item.length, item.addressType, target,
        state.a or 0, state.x or 0, sceneState(), mprString()
      ))
    end,
    emu.callbackType.exec,
    target, target, CPU, MEM
  )
end

local function onAdMemory(kind)
  local ordinal
  if kind == "AD_READ" then
    adReadOrdinal = adReadOrdinal + 1
    ordinal = adReadOrdinal
  else
    adWriteOrdinal = adWriteOrdinal + 1
    ordinal = adWriteOrdinal
  end
  local item = {
    kind=kind,
    ordinal=ordinal,
    startFrame=frame,
    adpcm=r16(0x20FC),
    memory=r16(0x20FA),
    length=r16(0x20F8),
    addressType=r8(0x20FF),
    returnTarget=stackReturnTarget(),
  }
  if not pendingAdMemoryByReturn[item.returnTarget] then
    pendingAdMemoryByReturn[item.returnTarget] = {}
  end
  table.insert(pendingAdMemoryByReturn[item.returnTarget], item)
  ensureAdMemoryReturnCallback(item.returnTarget)
  log(string.format(
    "[%s %03d] frame=%d adpcm=$%04X mem=$%04X bytes=$%04X " ..
    "type=$%02X caller_return=$%04X %s %s",
    kind, ordinal, frame, item.adpcm, item.memory, item.length,
    item.addressType, item.returnTarget, sceneState(), mprString()
  ))
end
local function ensureAdTransReturnCallback(target)
  if registeredAdTransReturns[target] then return end
  registeredAdTransReturns[target] = true
  emu.addMemoryCallback(
    function()
      local queue = pendingAdTransByReturn[target]
      if not queue or #queue == 0 then return end
      local item = table.remove(queue, 1)
      local elapsed = frame - item.startFrame
      addTransitionFrames("ad_trans", elapsed)
      local state = cpu()
      log(string.format(
        "[AD_TRANS_RETURN %03d] frame=%d elapsed_frames=%d elapsed_seconds=%.4f " ..
        "sector=$%06X blocks=$%02X adpcm_dest=$%04X set_addr=$%02X return=$%04X " ..
        "A=$%02X X=$%02X %s %s",
        item.ordinal, frame, elapsed, elapsed / 60.0,
        item.sector, item.blocks, item.destination, item.setAddress,
        target, state.a or 0, state.x or 0, sceneState(), mprString()
      ))
    end,
    emu.callbackType.exec,
    target, target, CPU, MEM
  )
end

local function onAdTrans()
  adTransOrdinal = adTransOrdinal + 1
  local item = {
    ordinal=adTransOrdinal,
    startFrame=frame,
    sector=(r8(0x20FC) << 16) | (r8(0x20FD) << 8) | r8(0x20FE),
    blocks=r8(0x20F8),
    destination=r16(0x20FA),
    setAddress=r8(0x20FF),
    returnTarget=stackReturnTarget(),
  }
  if not pendingAdTransByReturn[item.returnTarget] then
    pendingAdTransByReturn[item.returnTarget] = {}
  end
  table.insert(pendingAdTransByReturn[item.returnTarget], item)
  ensureAdTransReturnCallback(item.returnTarget)
  log(string.format(
    "[AD_TRANS %03d] frame=%d sector=$%06X blocks=$%02X adpcm_dest=$%04X " ..
    "set_addr=$%02X caller_return=$%04X %s %s",
    item.ordinal, frame, item.sector, item.blocks, item.destination,
    item.setAddress, item.returnTarget, sceneState(), mprString()
  ))
end

local function onAdStop()
  adStopCalls = adStopCalls + 1
  log(string.format("[AD_STOP %03d] frame=%d return=$%04X %s",
    adStopCalls, frame, stackReturnTarget(), sceneState()))
end

local function onAdStat()
  adStatCalls = adStatCalls + 1
  if adStatCalls <= 128 or adStatCalls % 64 == 0 then
    log(string.format("[AD_STAT %03d] frame=%d return=$%04X %s",
      adStatCalls, frame, stackReturnTarget(), sceneState()))
  end
end

local function onCdFade()
  cdFadeCalls = cdFadeCalls + 1
  local state = cpu()
  log(string.format("[CD_FADE %03d] frame=%d mode=$%02X return=$%04X %s",
    cdFadeCalls, frame, state.a or 0, stackReturnTarget(), sceneState()))
end

local function onVsync()
  vsyncCalls = vsyncCalls + 1
end

local function onModuleFadeCommand()
  -- Logical $80E7 belongs to the dialogue module only when the expected MPR
  -- bank is mapped.  Log MPRs so a reused logical address cannot be mistaken
  -- for the module during review.
  fadeCommandStartFrame = frame
  log(string.format(
    "[DIALOGUE_FADE_COMMAND] frame=%d state37F0=$%02X %s %s",
    frame, r8(0x37F0), sceneState(), mprString()
  ))
end

local function onModuleFadeClear()
  if fadeCommandStartFrame then
    log(string.format(
      "[DIALOGUE_FADE_CLEAR] frame=%d elapsed_frames=%d elapsed_seconds=%.4f " ..
      "state37F0=$%02X %s %s",
      frame, frame - fadeCommandStartFrame,
      (frame - fadeCommandStartFrame) / 60.0,
      r8(0x37F0), sceneState(), mprString()
    ))
  end
end

local function onFadeWaitLoop()
  if not fadeWaitStartFrame then
    fadeWaitStartFrame = frame
    fadeWaitSamples = 0
    log(string.format(
      "[FADE_WAIT_START] frame=%d state37F0=$%02X flag420B=$%02X %s %s",
      frame, r8(0x37F0), r8(0x420B), sceneState(), mprString()
    ))
  end
  fadeWaitSamples = fadeWaitSamples + 1
end

local function onFadeWaitExit()
  if fadeWaitStartFrame then
    local elapsed = frame - fadeWaitStartFrame
    if transitionWindow then
      transitionWindow.fade_wait_frames = transitionWindow.fade_wait_frames + elapsed
    end
    log(string.format(
      "[FADE_WAIT_END] frame=%d elapsed_frames=%d elapsed_seconds=%.4f " ..
      "loop_hits=%d state37F0=$%02X flag420B=$%02X %s %s",
      frame, elapsed,
      elapsed / 60.0,
      fadeWaitSamples, r8(0x37F0), r8(0x420B), sceneState(), mprString()
    ))
    fadeWaitStartFrame = nil
    fadeWaitSamples = 0
  end
end

local function onCdRead()
  readOrdinal = readOrdinal + 1
  local length = r16(0x20F8)
  local destination = r16(0x20FA)
  local lba = (r8(0x20FC) << 16) | (r8(0x20FD) << 8) | r8(0x20FE)
  local addressType = r8(0x20FF)
  local returnTarget = stackReturnTarget()
  local relative = lba - TRACK2_START_LBA
  local payloadOffset = relative >= 0 and relative * 0x800 or -1
  local unit = addressType == 0xFE and "bytes" or "sectors"

  if frame - lastCdFrame > 90 then
    log(string.format("[CD_BURST_START] frame=%d", frame))
  end
  lastCdFrame = frame

  local item = {
    ordinal=readOrdinal,
    startFrame=frame,
    sector=lba,
    addressType=addressType,
    destination=destination,
    length=length,
    unit=unit,
    returnTarget=returnTarget,
  }
  if not pendingReadsByReturn[returnTarget] then
    pendingReadsByReturn[returnTarget] = {}
  end
  table.insert(pendingReadsByReturn[returnTarget], item)
  ensureReturnCallback(returnTarget)

  log(string.format(
    "[CD_READ %03d] frame=%d sector=$%06X track2_payload_off=%s " ..
    "type=$%02X(%s) dest=$%04X len=$%04X_%s caller_return=$%04X %s %s",
    readOrdinal, frame, lba,
    payloadOffset >= 0 and string.format("$%08X", payloadOffset) or "outside_track2",
    addressType, addressTypeNames[addressType] or "UNKNOWN",
    destination, length, unit, returnTarget, sceneState(), mprString()
  ))
end

local function onByteLoader()
  byteLoaderOrdinal = byteLoaderOrdinal + 1
  local dest = r16(0x2000)
  local lba = (r8(0x2002) << 16) | (r8(0x2005) << 8) | r8(0x2004)
  local length = r16(0x2006)
  if lba == 0x1425 then
    transitionWindow = {
      startFrame=frame,
      startVsync=vsyncCalls,
      frames={cd_read=0, cd_exec=0, ad_trans=0, ad_read=0, ad_write=0},
      counts={cd_read=0, cd_exec=0, ad_trans=0, ad_read=0, ad_write=0},
      fade_wait_frames=0,
    }
    log(string.format("[TRANSITION_BUDGET_START] frame=%d sector=$%06X", frame, lba))
  end

  pendingByteLoader = {
    ordinal=byteLoaderOrdinal,
    startFrame=frame,
    dest=dest,
    lba=lba,
    length=length,
    callerReturn=stackReturnTarget(),
  }
  log(string.format(
    "[BYTE_LOADER %03d] frame=%d dest=$%04X sector=$%06X len=$%04X caller_return=$%04X %s %s",
    byteLoaderOrdinal, frame, dest, lba, length,
    pendingByteLoader.callerReturn, sceneState(), mprString()
  ))
end

local function onByteLoaderReturn()
  if not pendingByteLoader then return end
  local elapsed = frame - pendingByteLoader.startFrame
  log(string.format(
    "[BYTE_LOADER_RETURN %03d] frame=%d elapsed_frames=%d elapsed_seconds=%.4f " ..
    "dest=$%04X sector=$%06X len=$%04X caller_return=$%04X %s",
    pendingByteLoader.ordinal, frame, elapsed, elapsed / 60.0,
    pendingByteLoader.dest, pendingByteLoader.lba, pendingByteLoader.length,
    pendingByteLoader.callerReturn, sceneState()
  ))
  pendingByteLoader = nil
end

local function onParser()
  parserHits = parserHits + 1
  if transitionWindow then
    local total = frame - transitionWindow.startFrame
    local known = transitionWindow.frames.cd_read
      + transitionWindow.frames.cd_exec
      + transitionWindow.frames.ad_trans
      + transitionWindow.frames.ad_read
      + transitionWindow.frames.ad_write
      + transitionWindow.fade_wait_frames
    local residual = total - known
    log(string.format(
      "[TRANSITION_BUDGET] start_frame=%d ready_frame=%d total_frames=%d total_seconds=%.4f " ..
      "cd_read_frames=%d cd_read_calls=%d cd_exec_frames=%d cd_exec_calls=%d " ..
      "ad_trans_frames=%d ad_trans_calls=%d ad_read_frames=%d ad_read_calls=%d " ..
      "ad_write_frames=%d ad_write_calls=%d fade_wait_frames=%d vsync_calls=%d " ..
      "known_serial_frames=%d residual_frames=%d",
      transitionWindow.startFrame, frame, total, total / 60.0,
      transitionWindow.frames.cd_read, transitionWindow.counts.cd_read,
      transitionWindow.frames.cd_exec, transitionWindow.counts.cd_exec,
      transitionWindow.frames.ad_trans, transitionWindow.counts.ad_trans,
      transitionWindow.frames.ad_read, transitionWindow.counts.ad_read,
      transitionWindow.frames.ad_write, transitionWindow.counts.ad_write,
      transitionWindow.fade_wait_frames, vsyncCalls - transitionWindow.startVsync,
      known, residual
    ))
    transitionWindow = nil
  end
  if frame - lastParserFrame > 300 then
    dialogueGroups = dialogueGroups + 1
    log(string.format(
      "[DIALOGUE_READY %02d] frame=%d parser_hits=%d since_last_cd_frames=%d since_last_cd_seconds=%.4f %s",
      dialogueGroups, frame, parserHits,
      frame - lastCdFrame, (frame - lastCdFrame) / 60.0, sceneState()
    ))
  end
  lastParserFrame = frame
end

openLog()
log("Cyber City Oedo 808 CD transition profiler v2 armed.")
log("Read-only instrumentation: YES")
armCardRamMonitor()

emu.addMemoryCallback(onCdRead, emu.callbackType.exec, 0xE009, 0xE009, CPU, MEM)
emu.addMemoryCallback(onCdExec, emu.callbackType.exec, 0xE00F, 0xE00F, CPU, MEM)
emu.addMemoryCallback(onCdPlay, emu.callbackType.exec, 0xE012, 0xE012, CPU, MEM)
emu.addMemoryCallback(onCdPause, emu.callbackType.exec, 0xE018, 0xE018, CPU, MEM)
emu.addMemoryCallback(onAdTrans, emu.callbackType.exec, 0xE033, 0xE033, CPU, MEM)
emu.addMemoryCallback(function() onAdMemory("AD_READ") end, emu.callbackType.exec, 0xE036, 0xE036, CPU, MEM)
emu.addMemoryCallback(function() onAdMemory("AD_WRITE") end, emu.callbackType.exec, 0xE039, 0xE039, CPU, MEM)
emu.addMemoryCallback(onAdStop, emu.callbackType.exec, 0xE042, 0xE042, CPU, MEM)
emu.addMemoryCallback(onAdStat, emu.callbackType.exec, 0xE045, 0xE045, CPU, MEM)
emu.addMemoryCallback(onCdFade, emu.callbackType.exec, 0xE02D, 0xE02D, CPU, MEM)
emu.addMemoryCallback(onVsync, emu.callbackType.exec, 0xE07B, 0xE07B, CPU, MEM)
emu.addMemoryCallback(onModuleFadeCommand, emu.callbackType.exec, 0x80E7, 0x80E7, CPU, MEM)
emu.addMemoryCallback(onModuleFadeClear, emu.callbackType.exec, 0x8100, 0x8100, CPU, MEM)
emu.addMemoryCallback(onFadeWaitLoop, emu.callbackType.exec, 0x41EC, 0x41EC, CPU, MEM)
emu.addMemoryCallback(onFadeWaitExit, emu.callbackType.exec, 0x41F1, 0x41F1, CPU, MEM)
emu.addMemoryCallback(onByteLoader, emu.callbackType.exec, 0x6EA0, 0x6EA0, CPU, MEM)
emu.addMemoryCallback(onByteLoaderReturn, emu.callbackType.exec, 0x6EED, 0x6EED, CPU, MEM)
emu.addMemoryCallback(onParser, emu.callbackType.exec, 0x9543, 0x9543, CPU, MEM)

emu.addEventCallback(function()
  frame = frame + 1
  if frame % 600 == 0 then
    local pendingCount = 0
    for _,queue in pairs(pendingReadsByReturn) do
      pendingCount = pendingCount + #queue
    end
    log(string.format(
      "[HEARTBEAT] frame=%d reads=%d cd_exec=%d pending_reads=%d ad_trans=%d ad_read=%d ad_write=%d " ..
      "byte_loaders=%d dialogue_groups=%d vsync=%d %s",
      frame, readOrdinal, cdExecOrdinal, pendingCount, adTransOrdinal, adReadOrdinal, adWriteOrdinal,
      byteLoaderOrdinal, dialogueGroups, vsyncCalls, sceneState()
    ))
  end
end, emu.eventType.endFrame)

emu.addEventCallback(function()
  local pendingCount = 0
  for _,queue in pairs(pendingReadsByReturn) do
    pendingCount = pendingCount + #queue
  end
  log(string.format(
    "[SUMMARY] frames=%d reads=%d cd_exec=%d cd_play=%d cd_pause=%d pending_reads=%d ad_trans=%d ad_read=%d ad_write=%d ad_stop=%d " ..
    "ad_stat=%d cd_fade=%d vsync=%d byte_loaders=%d dialogue_groups=%d parser_hits=%d " ..
    "card_ram_size=%d card_ram_R/W/X=%d/%d/%d",
    frame, readOrdinal, cdExecOrdinal, cdPlayCalls, cdPauseCalls,
    pendingCount, adTransOrdinal, adReadOrdinal, adWriteOrdinal, adStopCalls,
    adStatCalls, cdFadeCalls, vsyncCalls, byteLoaderOrdinal, dialogueGroups, parserHits,
    cardRam.size, cardRam.R, cardRam.W, cardRam.X
  ))
  for i,sample in ipairs(cardRam.samples) do
    log(string.format("[CARD_RAM_SAMPLE %02d] %s", i, sample))
  end
  if logFile then
    logFile:flush()
    logFile:close()
    logFile = nil
  end
end, emu.eventType.scriptEnded)
