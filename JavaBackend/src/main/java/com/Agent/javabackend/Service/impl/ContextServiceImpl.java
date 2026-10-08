package com.Agent.javabackend.Service.impl;

import com.Agent.javabackend.Service.ContextService;
import com.Agent.javabackend.dto.ConversationDTO.ContextMessage;
import com.Agent.javabackend.dto.RunStatus;
import com.Agent.javabackend.entity.MessageContainer.AgentTask;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Service
public class ContextServiceImpl implements ContextService {
    /**
     * 一次请求最多带多少个历史问答轮次。
     * 每轮会转换成两条消息：一条 user，一条 assistant。
     */
    private final int maxContextTurns;

    public ContextServiceImpl(
            @Value("${agent.context.max-turns:10}") int maxContextTurns) {
        if (maxContextTurns < 0) {
            throw new IllegalArgumentException("agent.context.max-turns 不能小于 0");
        }
        this.maxContextTurns = maxContextTurns;
    }

    @Override
    public List<ContextMessage> assembleContext(List<AgentTask> previous) {
        if (previous == null || previous.isEmpty() || maxContextTurns == 0) {
            return List.of();
        }

        // previous 已由 Mapper 按创建时间从早到晚提供，因此这里保持原顺序。
        // 只有已经完成、同时有问题和回答的任务，才算一轮可以使用的历史。
        List<AgentTask> completedTurns = previous.stream()
                .filter(this::isCompleteTurn)
                .toList();

        int firstTurn = Math.max(0, completedTurns.size() - maxContextTurns);
        List<ContextMessage> context = new ArrayList<>();
        for (AgentTask task : completedTurns.subList(firstTurn, completedTurns.size())) {
            context.add(new ContextMessage("user", task.getPrompt()));
            context.add(new ContextMessage("assistant", task.getResult()));
        }

        return List.copyOf(context);
    }

    /** 一轮任务必须同时具备完成状态、用户问题和 Agent 回答。 */
    private boolean isCompleteTurn(AgentTask task) {
        return task != null
                && task.getStatus() == RunStatus.COMPLETED
                && hasText(task.getPrompt())
                && hasText(task.getResult());
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
