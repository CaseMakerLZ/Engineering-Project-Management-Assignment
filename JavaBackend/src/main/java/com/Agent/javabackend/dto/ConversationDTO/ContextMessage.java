package com.Agent.javabackend.dto.ConversationDTO;

/** 发给 Python Agent 的一条历史对话内容。 */
public record ContextMessage(
        /** 谁说的：user 表示用户，assistant 表示 Agent。 */
        String role,
        /** 这条历史消息的文字内容。 */
        String content) {}
