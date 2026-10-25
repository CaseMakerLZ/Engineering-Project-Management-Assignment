package com.Agent.javabackend.dto.AuthDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/** 认证接口可以对外暴露的最小用户信息。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class UserResponse {
    @JsonProperty("user_id")
    private String userId;

    private String username;
}
