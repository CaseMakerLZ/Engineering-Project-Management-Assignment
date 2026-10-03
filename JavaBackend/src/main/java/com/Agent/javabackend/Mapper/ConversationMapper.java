package com.Agent.javabackend.Mapper;

import com.Agent.javabackend.entity.MessageContainer.Conversation;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Optional;

/** Conversation 表的数据访问接口；SQL 位于 resources/mapper/ConversationMapper.xml。 */
@Mapper
public interface ConversationMapper {
    int insert(Conversation conversation);
    Optional<Conversation> findById(@Param("conversationId") String conversationId);
    List<Conversation> findByProjectId(@Param("projectId") String projectId);
}
