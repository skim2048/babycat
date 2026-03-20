<template>
  <div class="state-bar">
    <div class="cam-info">
      <img src="/icons/Home/Camera_Line.svg" alt="카메라" />
      <img class="dot" src="/icons/Home/DoubleDot.svg" alt="" />
      <b>101</b>
    </div>
    <b>2026.03.19. 10:30:47</b>
  </div>
</template>

<style scoped>
.state-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 19px;
  height: 30px;
  flex-shrink: 0;
  font-size: 10.79px;
  color: #84776e;
  font-family: 'Hancom MalangMalang', sans-serif;
}

.cam-info {
  display: flex;
  align-items: center;
  gap: 4px;
}

.cam-info img {
  width: 16px;
  height: 16px;
}

.cam-info .dot {
  width: 6px;
  height: 6px;
}
</style>
