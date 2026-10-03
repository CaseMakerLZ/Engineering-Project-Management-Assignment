package com.Agent.javabackend.Service.impl;

import com.Agent.javabackend.Service.ContextService;
import com.Agent.javabackend.dto.ConversationDTO.ContextMessage;
import com.Agent.javabackend.dto.RunStatus;
import com.Agent.javabackend.entity.MessageContainer.AgentTask;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Service
public class ContextServiceImpl implements ContextService {
    // Question: 这种有关配置的数值应该最后要统一到一个文件中去（放yaml里面吗——我认为有点奇怪，还是说单开一个文件统一放？）
    // 而且python AgentCore中的这个20的限制也要变成可配置项，总之类似地数据绝对不能硬编码
    public static final int maxContextMessages = 20;

    // 对话上下文只取已完成轮次的用户问题和最终回答；工具日志不属于聊天内容。
    @Override
    public List<ContextMessage> assembleContext(List<AgentTask> previous) {
        List<ContextMessage> context = new ArrayList<>();
        for(AgentTask task: previous){
            if(task.getStatus() == RunStatus.COMPLETED && task.getResult() != null){
                context.add(new ContextMessage("user", task.getPrompt()));
                context.add(new ContextMessage("assistant", task.getResult()));
            }
        }
        // 本项目暂定最多传 20 条历史消息，与 Python 请求模型的 max_length 保持一致。
        // 每个已完成 Turn 对应两条消息，因此这里最多保留最近 10 轮。
        if(context.size() > maxContextMessages){
            context = new ArrayList<>(context.subList(context.size() - maxContextMessages, context.size()));
        }

        return context;
    }
}
