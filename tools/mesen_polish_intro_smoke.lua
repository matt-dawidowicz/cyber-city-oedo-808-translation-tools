-- Exact repeatable MesenCE 2.2.1 New Game + Mission 0 diagnostic smoke.
-- Read-only for game memory; only supplies known test controller inputs.
-- Does NOT prove bartender access, audio continuity or any cache lifecycle.
-- Enable --pcEngine.port1.type=PceController and --enableStdout.
local frame = 0
local redirects = 0
local pool_loads = 0
local dispatches = 0

emu.addEventCallback(function()
    local input = {}
    if frame >= 90 and frame < 195 then input.run = true end
    if frame >= 700 and frame < 735 then input.i = true end
    emu.setInput(input, 0, 0)
end, emu.eventType.inputPolled)

emu.addMemoryCallback(function()
    local cpu = emu.getCpuState(emu.cpuType.pce)
    dispatches = dispatches + 1
    if cpu.a == 0x7B then
        redirects = redirects + 1
        print(string.format("NATIVE_7B frame=%d pc=B17A", frame))
    end
end, emu.callbackType.exec, 0xB17A, 0xB17A,
    emu.cpuType.pce, emu.memType.pceMemory)

emu.addMemoryCallback(function()
    pool_loads = pool_loads + 1
    print(string.format("POOL_LOAD frame=%d", frame))
end, emu.callbackType.exec, 0xB26E, 0xB26E,
    emu.cpuType.pce, emu.memType.pceMemory)

emu.addEventCallback(function()
    frame = frame + 1
    if frame == 600 or frame == 4200 or frame == 4600 then
        print(string.format(
            "POLISH_CHECKPOINT frame=%d dispatch=%d redirect=%d loads=%d",
            frame, dispatches, redirects, pool_loads
        ))
    end
    if frame >= 4600 then
        print(string.format(
            "POLISH_INTRO_DONE frames=%d redirects=%d loads=%d",
            frame, redirects, pool_loads
        ))
        -- Only the caller, by inspecting Mesen's *own SCSI log*,
        -- can assert no bad optical reads occurred.
        emu.stop(0)
    end
end, emu.eventType.endFrame)
