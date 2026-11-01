package com.Agent.javabackend.Service;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * 按 SSE 空行边界聚合完整帧。
 *
 * 一个 frame 可以包含 event、id、多条 data 和注释；这里不把单行
 * 当成完整 JSON，也不把尚未结束的数据无限保存。
 */
final class SseFrameParser {
    private final int maxFrameBytes;
    private final List<String> lines = new ArrayList<>();
    private int frameBytes;

    SseFrameParser(int maxFrameBytes) {
        this.maxFrameBytes = maxFrameBytes;
    }

    /** 返回 null 表示帧尚未结束；空行会触发帧解析。 */
    Frame acceptLine(String line) {
        if (line == null) {
            return null;
        }
        if (line.isEmpty()) {
            if (lines.isEmpty()) {
                return null;
            }
            Frame frame = buildFrame();
            reset();
            return frame;
        }

        int bytes = line.getBytes(StandardCharsets.UTF_8).length + 1;
        if (frameBytes + bytes > maxFrameBytes) {
            reset();
            throw new FrameTooLargeException();
        }
        lines.add(line);
        frameBytes += bytes;
        return null;
    }

    /** 上游在最后一个空行前结束时，尽量处理已经收到的完整字段。 */
    Frame finish() {
        if (lines.isEmpty()) {
            return null;
        }
        Frame frame = buildFrame();
        reset();
        return frame;
    }

    private Frame buildFrame() {
        String event = null;
        String id = null;
        StringBuilder data = null;
        List<String> comments = new ArrayList<>();

        for (String line : lines) {
            if (line.startsWith(":")) {
                comments.add(line.substring(1));
                continue;
            }
            int colon = line.indexOf(':');
            String field = colon < 0 ? line : line.substring(0, colon);
            String value = colon < 0 ? "" : line.substring(colon + 1);
            if (value.startsWith(" ")) {
                value = value.substring(1);
            }
            switch (field) {
                case "event" -> event = value;
                case "id" -> id = value;
                case "data" -> {
                    if (data == null) {
                        data = new StringBuilder(value);
                    } else {
                        data.append('\n').append(value);
                    }
                }
                default -> {
                    // retry 等字段当前不需要展示，也不影响帧边界。
                }
            }
        }
        return new Frame(event, id, data == null ? null : data.toString(), List.copyOf(comments));
    }

    private void reset() {
        lines.clear();
        frameBytes = 0;
    }

    record Frame(String event, String id, String data, List<String> comments) {
        boolean hasData() {
            return data != null;
        }

        boolean isCommentOnly() {
            return data == null && !comments.isEmpty();
        }
    }

    static final class FrameTooLargeException extends RuntimeException {
    }
}
