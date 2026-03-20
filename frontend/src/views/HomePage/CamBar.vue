<template>
  <div :class="$style.camBar">
    <img :class="$style.iconCameraFill" src="/icons/Home/Camera_Fill.svg" alt="카메라" />
    <img :class="$style.iconVideoFill" src="/icons/Home/Video_Fill.svg" alt="영상" />
    <img :class="$style.iconDirectionFill" src="/icons/Home/Direction_Fill.svg" alt="방향" />
    <img :class="$style.iconRestartFill" src="/icons/Home/Restart_Fill.svg" alt="새로고침" />
  </div>
</template>

<style module>
.camBar {
  width: 100%;
  height: 56px;
  position: relative;
  background-color: rgba(255, 255, 255, 0);
  overflow: hidden;
}
.iconCameraFill {
  position: absolute;
  top: calc(50% - 13px);
  left: calc(50% - 140px);
  width: 25px;
  height: 25px;
}
.iconVideoFill {
  position: absolute;
  top: calc(50% - 13px);
  left: calc(50% - 55px);
  width: 25px;
  height: 25px;
}
.iconRestartFill {
  position: absolute;
  top: 15px;
  left: 297px;
  width: 25px;
  height: 25px;
}
.iconDirectionFill {
  position: absolute;
  top: 15px;
  left: 211px;
  width: 25px;
  height: 25px;
}
</style>
