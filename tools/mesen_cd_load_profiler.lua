-- Cyber City Oedo 808 - CD load timing profiler
-- Mesen 2.2.1 / PC Engine CD
--
-- READ ONLY. This captures the exact System Card CD_READ request stream,
-- scene selectors, MPR state, caller return targets, complete exploration
-- setup phases, transition-to-interactive latency, and activity in physical
-- CD-RAM bank $87. It does not alter RAM, MPRs, disc state, or the System Card.
--
-- Recommended coverage:
--   enter bar -> talk to bartender/Mama -> leave -> enter another room ->
--   return to bar -> repeat one interaction.
--
-- Persistent log: cyber_oedo_cd_load_profile.log

local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory
local CDRAM = emu.memType.pceCdromRam

local TRACK2_START_LBA = 3590
local frame = 0
local reads = 0
local transferredBytes = 0
local loaderEntries = 0
local explorationEntries = 0
local sceneSetups = 0
local pendingTransition = nil
local pendingExploration = nil
local pendingSetup = nil
local pendingDialogueLoad = nil
local pendingDialogueExit = nil
local dialogueLoads = 0
local bank87 = {R=0,W=0,X=0}
local logFile = nil
local pendingSceneRead = nil

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
  logFile = io.open(base .. "/cyber_oedo_cd_load_profile.log", "a")
  if logFile then
    logFile:write("\n=== NEW CD LOAD PROFILE SESSION ===\n")
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

local function sceneState()
  return string.format(
    "scene=$%02X room=$%02X resume=$%02X transition=%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X",
    r8(0x3700), r8(0x3701), r8(0x3702),
    r8(0x3703), r8(0x3704), r8(0x3705), r8(0x3706),
    r8(0x3707), r8(0x3708), r8(0x3709), r8(0x370A), r8(0x370B)
  )
end

local addressTypeNames = {
  [0x00]="LOCAL_BYTES",
  [0x01]="LOCAL_SECTORS",
  [0x02]="BANK_MPR2",
  [0x03]="BANK_MPR3",
  [0x04]="BANK_MPR4",
  [0x05]="BANK_MPR5",
  [0x06]="BANK_MPR6",
  [0xFE]="VRAM_BYTES",
  [0xFF]="VRAM_SECTORS",
}

local function onCdRead()
  reads = reads + 1
  local length = r16(0x20F8)
  local destination = r16(0x20FA)
  local lba = (r8(0x20FC) << 16) | (r8(0x20FD) << 8) | r8(0x20FE)
  local addressType = r8(0x20FF)
  local relative = lba - TRACK2_START_LBA
  local payloadOffset = relative >= 0 and relative * 0x800 or -1
  local unit = (addressType == 0x00 or addressType == 0xFE) and "bytes" or "sectors"
  local transferBytes = unit == "bytes" and length or (length * 0x800)
  transferredBytes = transferredBytes + transferBytes
  local state = cpu()
  local returnTarget = stackReturnTarget()
  if returnTarget == 0x48CD and lba == 0x1425 then
    dialogueLoads = dialogueLoads + 1
    pendingDialogueLoad = {
      frame=frame,
      counters=snapshotCounters and snapshotCounters() or {reads=reads-1, bytes=transferredBytes-transferBytes, loaders=loaderEntries},
    }
    log(string.format(
      "[DIALOGUE_LOAD_START %03d] frame=%d sector=$%06X %s %s",
      dialogueLoads, frame, lba, sceneState(), mprString()
    ))
  end
  if returnTarget == 0x425E or returnTarget == 0x428A then
    pendingSceneRead = {
      ordinal=reads,
      startFrame=frame,
      returnTarget=returnTarget,
      sector=lba,
      addressType=addressType,
      destination=destination,
      length=length,
    }
  end
  log(string.format(
    "[CD_READ %03d] frame=%d sector=$%06X track2_payload_off=%s type=$%02X(%s) dest=$%04X len=$%04X_%s caller_return=$%04X PC=$%04X %s %s",
    reads, frame, lba,
    payloadOffset >= 0 and string.format("$%08X", payloadOffset) or "outside_track2",
    addressType, addressTypeNames[addressType] or "UNKNOWN",
    destination, length, unit, returnTarget, state.pc or 0,
    sceneState(), mprString()
  ))
end


local function onSceneReadReturn()
  if not pendingSceneRead then return end
  local state = cpu()
  local elapsed = frame - pendingSceneRead.startFrame
  log(string.format(
    "[SCENE_READ_RETURN %03d] frame=%d elapsed_frames=%d elapsed_seconds=%.4f sector=$%06X type=$%02X dest=$%04X len=$%04X return=$%04X A=$%02X X=$%02X %s",
    pendingSceneRead.ordinal, frame, elapsed, elapsed / 60.0,
    pendingSceneRead.sector, pendingSceneRead.addressType,
    pendingSceneRead.destination, pendingSceneRead.length,
    pendingSceneRead.returnTarget, state.a or 0, state.x or 0,
    sceneState()
  ))
  pendingSceneRead = nil
end

local function onByteLoader()
  loaderEntries = loaderEntries + 1
  local dest = r16(0x2000)
  local lba = (r8(0x2002) << 16) | (r8(0x2005) << 8) | r8(0x2004)
  local length = r16(0x2006)
  log(string.format(
    "[BYTE_LOADER %03d] frame=%d dest=$%04X sector=$%06X len=$%04X return=$%04X %s %s",
    loaderEntries, frame, dest, lba, length, stackReturnTarget(),
    sceneState(), mprString()
  ))
end

local function bank87Event(kind)
  bank87[kind] = bank87[kind] + 1
end

local function snapshotCounters()
  return {
    reads=reads,
    bytes=transferredBytes,
    loaders=loaderEntries,
  }
end

local function deltaCounters(start)
  return reads - start.reads, transferredBytes - start.bytes, loaderEntries - start.loaders
end

local function logPhase(tag, start)
  local readDelta, byteDelta, loaderDelta = deltaCounters(start.counters)
  local elapsed = frame - start.frame
  log(string.format(
    "[%s] frame=%d elapsed_frames=%d elapsed_seconds=%.4f reads=%d bytes=%d loaders=%d %s %s",
    tag, frame, elapsed, elapsed / 60.0,
    readDelta, byteDelta, loaderDelta, sceneState(), mprString()
  ))
end

local function onExplorationEntry()
  explorationEntries = explorationEntries + 1
  pendingExploration = {
    frame=frame,
    counters=snapshotCounters(),
  }
  log(string.format(
    "[EXPLORATION_ENTRY %03d] frame=%d %s %s",
    explorationEntries, frame, sceneState(), mprString()
  ))
end

local function onSceneSetupStart()
  if pendingDialogueExit then
    logPhase("DIALOGUE_END_TO_SCENE_SETUP", pendingDialogueExit)
    pendingDialogueExit = nil
  end
  sceneSetups = sceneSetups + 1
  pendingSetup = {
    frame=frame,
    counters=snapshotCounters(),
  }
  log(string.format(
    "[SCENE_SETUP_START %03d] frame=%d %s %s",
    sceneSetups, frame, sceneState(), mprString()
  ))
end

local function onSceneSetupPhase(tag)
  if pendingSetup then
    logPhase(tag, pendingSetup)
  end
end

local function onInteractiveLoop()
  if pendingSetup then
    logPhase("SCENE_SETUP_TO_INTERACTIVE", pendingSetup)
    pendingSetup = nil
  end
  if pendingExploration then
    logPhase("EXPLORATION_ENTRY_TO_INTERACTIVE", pendingExploration)
    pendingExploration = nil
  end
  if pendingTransition then
    logPhase("TRANSITION_TO_INTERACTIVE", pendingTransition)
    pendingTransition = nil
  end
end

local function onDialogueParser()
  local pointer = r16(0x007F)
  local opcode = r8(pointer)
  if pendingDialogueLoad then
    logPhase("DIALOGUE_LOAD_TO_FIRST_PARSER", pendingDialogueLoad)
    pendingDialogueLoad = nil
  end
  if opcode == 0x00 then
    pendingDialogueExit = {
      frame=frame,
      counters=snapshotCounters(),
    }
    log(string.format(
      "[DIALOGUE_STREAM_END] frame=%d ptr=$%04X voice=$%02X %s %s",
      frame, pointer, r8(0x37F1), sceneState(), mprString()
    ))
  end
end

local function onTransitionExit()
  if r8(0x2649) == 0 then return end
  pendingTransition = {
    frame=frame,
    counters=snapshotCounters(),
  }
  log(string.format(
    "[TRANSITION_EXIT] frame=%d exit_flag=$%02X %s %s",
    frame, r8(0x2649), sceneState(), mprString()
  ))
end

openLog()
log("Cyber City Oedo 808 CD load profiler armed. Read-only instrumentation: YES")

emu.addMemoryCallback(onCdRead, emu.callbackType.exec, 0xE009, 0xE009, CPU, MEM)
emu.addMemoryCallback(onSceneReadReturn, emu.callbackType.exec, 0x425E, 0x425E, CPU, MEM)
emu.addMemoryCallback(onSceneReadReturn, emu.callbackType.exec, 0x428A, 0x428A, CPU, MEM)
emu.addMemoryCallback(onByteLoader, emu.callbackType.exec, 0x6EA0, 0x6EA0, CPU, MEM)
emu.addMemoryCallback(onExplorationEntry, emu.callbackType.exec, 0x4000, 0x4000, CPU, MEM)
emu.addMemoryCallback(onSceneSetupStart, emu.callbackType.exec, 0x40E9, 0x40E9, CPU, MEM)
emu.addMemoryCallback(function() onSceneSetupPhase("SCENE_DESCRIPTOR_DONE") end, emu.callbackType.exec, 0x40EC, 0x40EC, CPU, MEM)
emu.addMemoryCallback(function() onSceneSetupPhase("SCENE_HEADER_DONE") end, emu.callbackType.exec, 0x40EF, 0x40EF, CPU, MEM)
emu.addMemoryCallback(function() onSceneSetupPhase("SCENE_DIMENSIONS_DONE") end, emu.callbackType.exec, 0x40F2, 0x40F2, CPU, MEM)
emu.addMemoryCallback(function() onSceneSetupPhase("ROOM_DESCRIPTOR_DONE") end, emu.callbackType.exec, 0x40F5, 0x40F5, CPU, MEM)
emu.addMemoryCallback(function() onSceneSetupPhase("ROOM_AUX_LOAD_DONE") end, emu.callbackType.exec, 0x40F8, 0x40F8, CPU, MEM)
emu.addMemoryCallback(onInteractiveLoop, emu.callbackType.exec, 0x4012, 0x4012, CPU, MEM)
emu.addMemoryCallback(onTransitionExit, emu.callbackType.exec, 0x402B, 0x402B, CPU, MEM)
emu.addMemoryCallback(onDialogueParser, emu.callbackType.exec, 0x9543, 0x9543, CPU, MEM)

local bank87Start = (0x87 - 0x80) * 0x2000
local bank87End = bank87Start + 0x1FFF
emu.addMemoryCallback(function() bank87Event("R") end, emu.callbackType.read, bank87Start, bank87End, CPU, CDRAM)
emu.addMemoryCallback(function() bank87Event("W") end, emu.callbackType.write, bank87Start, bank87End, CPU, CDRAM)
emu.addMemoryCallback(function() bank87Event("X") end, emu.callbackType.exec, bank87Start, bank87End, CPU, CDRAM)

emu.addEventCallback(function()
  frame = frame + 1
  if frame % 600 == 0 then
    log(string.format(
      "[HEARTBEAT] frame=%d reads=%d bytes=%d loader_entries=%d bank87_R/W/X=%d/%d/%d %s",
      frame, reads, transferredBytes, loaderEntries, bank87.R, bank87.W, bank87.X, sceneState()
    ))
  end
end, emu.eventType.endFrame)

emu.addEventCallback(function()
  log(string.format(
    "[SUMMARY] frames=%d reads=%d bytes=%d loader_entries=%d exploration_entries=%d scene_setups=%d dialogue_loads=%d bank87_R/W/X=%d/%d/%d",
    frame, reads, transferredBytes, loaderEntries, explorationEntries, sceneSetups, dialogueLoads, bank87.R, bank87.W, bank87.X
  ))
  if logFile then
    logFile:flush()
    logFile:close()
    logFile = nil
  end
end, emu.eventType.scriptEnded)
