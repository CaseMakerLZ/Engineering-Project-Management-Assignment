package com.Agent.javabackend.Mapper;

import com.Agent.javabackend.entity.MessageContainer.AgentTask;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Optional;

/** AgentTask 表的数据访问接口；SQL 位于 resources/mapper/AgentTaskMapper.xml。 */
@Mapper
public interface AgentTaskMapper {
    int insert(AgentTask task);
    int updateExecution(AgentTask task);
    Optional<AgentTask> findById(@Param("taskId") String taskId);
    List<AgentTask> findByConversationId(@Param("conversationId") String conversationId);
}
