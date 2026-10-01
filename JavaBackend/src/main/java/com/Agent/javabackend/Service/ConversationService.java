package com.Agent.javabackend.Service;

import com.Agent.javabackend.dto.ConversationDTO.*;

public interface ConversationService {
    ConversationResponse create(String projectId, CreateConversationRequest request);
    ConversationResponse get(String conversationId);
    java.util.List<ConversationResponse> list(String projectId);
    CreateTurnResponse createTurn(String conversationId, CreateTurnRequest request);
    TurnResponse getTurn(String conversationId, String taskId);
    java.util.List<TurnResponse> listTurns(String conversationId);
}
