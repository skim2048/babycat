<template>
  <div :class="$style.stateBar">
    <img :class="$style.iconCameraLine" src="/icons/Home/Camera_Line.svg" alt="카메라" />
    <img :class="$style.iconDoubledot" src="/icons/Home/DoubleDot.svg" alt="" />
    <b :class="$style.camName">101</b>
    <b :class="$style.time">2026.03.19. 10:30:47</b>
  </div>
</template>

<style module>
.stateBar {
  width: 100%;
  height: 30px;
  position: relative;
  background-color: rgba(255, 255, 255, 0);
  overflow: hidden;
  font-size: 10.79px;
  color: #84776e;
  font-family: 'Hancom MalangMalang', sans-serif;
}
.time {
  position: absolute;
  top: 9px;
  left: 228px;
  display: inline-block;
  width: 112px;
  height: 11px;
}
.camName {
  position: absolute;
  top: 9px;
  left: 41px;
  display: inline-block;
  text-align: left;
  width: 17px;
  height: 11px;
}
.iconCameraLine {
  position: absolute;
  top: 7px;
  left: 19px;
  width: 16px;
  height: 16px;
}
.iconDoubledot {
  position: absolute;
  top: 13px;
  left: 35px;
  width: 6px;
  height: 6px;
}
</style>
