#include "fs_lock.h"

SemaphoreHandle_t gFsMutex = nullptr;

void fsLockInit() {
    gFsMutex = xSemaphoreCreateMutex();
}
