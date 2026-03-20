<template>
  <div class="cam-bar">
    <img src="/icons/Home/Camera_Fill.svg" alt="카메라" />
    <img src="/icons/Home/Video_Fill.svg" alt="영상" />
    <img src="/icons/Home/Direction_Fill.svg" alt="방향" />
    <img src="/icons/Home/Restart_Fill.svg" alt="새로고침" />
  </div>
</template>

<style scoped>
.cam-bar {
  display: flex;
  align-items: center;
  justify-content: space-evenly;
  height: 56px;
  flex-shrink: 0;
}

.cam-bar img {
  width: 25px;
  height: 25px;
}
</style>
