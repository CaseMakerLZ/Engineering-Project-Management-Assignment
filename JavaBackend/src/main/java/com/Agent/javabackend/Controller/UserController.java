package com.Agent.javabackend.Controller;

import com.Agent.javabackend.dto.Result;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController("/api/auth")
public class UserController {
    @PostMapping("/register")
    public Result<User> register(){

        return
    }

}
