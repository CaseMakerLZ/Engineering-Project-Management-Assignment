package com.Agent.javabackend.Config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class Config {
    @Bean
    public RestClient agentRestClient(@Value("${agent-service.base-url}") String baseUrl,
                                      @Value("${agent-service.internal-token}")String token){
        RestClient.Builder builder = RestClient.builder()
                .baseUrl(baseUrl);

        if (!token.isBlank()) {
            builder.defaultHeader("X-Service-Token", token);
        }

        return builder.build();
    }
}
