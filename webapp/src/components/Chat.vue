<template>
  <button class="chat-btn" aria-label="채팅">
    <img src="/icons/Chat_Fill.svg" alt="채팅" />
  </button>
</template>

<style scoped>
.chat-btn {
  position: fixed;
  right: 16px;
  bottom: calc(var(--nav-height) + 16px);
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background-color: #fffbf5;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.chat-btn img {
  width: 22px;
  height: 22px;
}
</style>
