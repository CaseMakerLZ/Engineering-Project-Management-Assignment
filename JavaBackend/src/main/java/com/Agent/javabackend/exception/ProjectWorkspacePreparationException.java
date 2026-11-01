package com.Agent.javabackend.exception;

import lombok.Getter;

/** 项目已经落库，但 Python 工作区准备失败。 */
@Getter
public class ProjectWorkspacePreparationException extends BaseException {
    private final String projectId;

    public ProjectWorkspacePreparationException(String projectId, String message, Throwable cause) {
        super(ErrorCode.PROJECT_WORKSPACE_PREPARATION_FAILED, message, cause);
        this.projectId = projectId;
    }
}
