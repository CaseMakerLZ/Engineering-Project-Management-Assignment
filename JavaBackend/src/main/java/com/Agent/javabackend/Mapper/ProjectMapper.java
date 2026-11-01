package com.Agent.javabackend.Mapper;

import com.Agent.javabackend.entity.MessageContainer.Project;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.Optional;
import java.util.List;

/** Project 表的数据访问接口；SQL 位于 resources/mapper/ProjectMapper.xml。 */
@Mapper
public interface ProjectMapper {
    int insert(Project project);
    Optional<Project> findById(@Param("projectId") String projectId);
    Optional<Project> findByIdAndOwnerId(
            @Param("projectId") String projectId,
            @Param("ownerId") String ownerId);
    List<Project> findAllByOwnerId(@Param("ownerId") String ownerId);
}
