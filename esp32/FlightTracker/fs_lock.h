#pragma once
#ifndef FT_FS_LOCK_H
#define FT_FS_LOCK_H

#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

// Guards every LittleFS file operation reachable from more than one task.
// fetchTask() (its own FreeRTOS task, pinned to a separate core — see
// FlightTracker.ino) writes the route/airport cache; the main loop() task
// writes logo files (POST /config, POST /logos) and reads them back every
// render. LittleFS is not guaranteed safe for concurrent access from two
// different tasks, even when they touch completely different files — block
// allocation and wear-leveling metadata is shared filesystem-wide. Without
// this, a write on one core racing a read/write on the other can leave a
// file that still opens fine (so drawLogo() logs a HIT, not a MISS) but
// reads back truncated or zeroed — a logo that's "recognized" but renders
// as solid black.
extern SemaphoreHandle_t gFsMutex;

void fsLockInit();

// RAII guard — take on construction, release on destruction, so an early
// return from the guarded function can't leave the mutex held.
class FsLock {
public:
    FsLock()  { if (gFsMutex) xSemaphoreTake(gFsMutex, portMAX_DELAY); }
    ~FsLock() { if (gFsMutex) xSemaphoreGive(gFsMutex); }
    FsLock(const FsLock&) = delete;
    FsLock& operator=(const FsLock&) = delete;
};

#endif // FT_FS_LOCK_H
