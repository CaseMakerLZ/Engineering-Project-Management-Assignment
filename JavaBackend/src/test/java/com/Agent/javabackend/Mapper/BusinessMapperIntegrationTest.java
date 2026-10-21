package com.Agent.javabackend.Mapper;

import com.Agent.javabackend.entity.MessageContainer.AgentTask;
import com.Agent.javabackend.entity.MessageContainer.Conversation;
import com.Agent.javabackend.entity.MessageContainer.Project;
import com.Agent.javabackend.dto.RunStatus;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

/** 使用默认 local profile 的 SQLite，验证 MyBatis XML Mapper 的写入、查询和更新。 */
@SpringBootTest
@Transactional
class BusinessMapperIntegrationTest {
    @Autowired private ProjectMapper projects;
    @Autowired private ConversationMapper conversations;
    @Autowired private AgentTaskMapper tasks;
    @Autowired private JdbcTemplate jdbcTemplate;

    @Test
    void projectConversationAndTaskRoundTrip() {
        OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
        Project project = new Project();
        project.setId(UUID.randomUUID().toString());
        project.setName("integration test");
        project.setLocalPath(java.nio.file.Path.of(".").toAbsolutePath().normalize().toString());
        project.setCreatedAt(now);
        project.setUpdatedAt(now);
        projects.insert(project);
        assertEquals(project.getName(), projects.findById(project.getId()).orElseThrow().getName());

        Conversation conversation = new Conversation();
        conversation.setId(UUID.randomUUID().toString());
        conversation.setProjectId(project.getId());
        conversation.setTitle("round trip");
        conversation.setStatus("ACTIVE");
        conversation.setCreatedAt(now);
        conversation.setUpdatedAt(now);
        conversations.insert(conversation);
        assertEquals(1, conversations.findByProjectId(project.getId()).size());

        AgentTask task = new AgentTask();
        task.setId(UUID.randomUUID().toString());
        task.setConversationId(conversation.getId());
        task.setPrompt("first question");
        task.setPythonRunId(UUID.randomUUID().toString());
        task.setStatus(RunStatus.CREATED);
        task.setCreatedAt(now);
        // Java 实际流程会先调用 Python 创建 agent_run，再插入 agent_task；
        // 这里用同一个 SQLite 数据库补齐这个跨服务前置记录。
        jdbcTemplate.update(
                "INSERT INTO agent_run " +
                        "(run_id, project_id, conversation_id, prompt, context_json, status, " +
                        "result, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                task.getPythonRunId(), project.getId(), conversation.getId(),
                task.getPrompt(), "[]", RunStatus.CREATED.name(), null, null, now.toString());
        tasks.insert(task);
        assertEquals(RunStatus.CREATED, tasks.findById(task.getId()).orElseThrow().getStatus());

        task.setStatus(RunStatus.COMPLETED);
        task.setResult("first answer");
        task.setFinishedAt(now);
        tasks.updateExecution(task);
        assertEquals("first answer", tasks.findByConversationId(conversation.getId()).getFirst().getResult());
    }
}
