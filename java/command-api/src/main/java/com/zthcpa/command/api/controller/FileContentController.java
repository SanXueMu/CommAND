package com.zthcpa.command.api.controller;

import org.springframework.core.io.InputStreamResource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.UUID;

/** Controlled browser file boundary. Paths are always relative to COMMAND_DATA_DIR. */
@RestController
@RequestMapping("/api/files")
public final class FileContentController {
    private final Path dataDirectory;

    public FileContentController() {
        this(Path.of(System.getenv().getOrDefault("COMMAND_DATA_DIR", "data")));
    }

    FileContentController(Path dataDirectory) {
        this.dataDirectory = dataDirectory.toAbsolutePath().normalize();
    }

    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, Object> upload(@RequestParam("file") MultipartFile file) throws IOException {
        if (file == null || file.isEmpty()) throw new IllegalArgumentException("file must not be empty");
        String originalName = Path.of(file.getOriginalFilename() == null ? "upload.bin" : file.getOriginalFilename())
                .getFileName().toString();
        String safeName = originalName.replaceAll("[^A-Za-z0-9._-]", "_");
        if (safeName.isBlank()) safeName = "upload.bin";
        Path target = dataDirectory.resolve("uploads").resolve(UUID.randomUUID() + "-" + safeName).normalize();
        if (!target.startsWith(dataDirectory)) throw new IllegalArgumentException("invalid upload path");
        Files.createDirectories(target.getParent());
        try (InputStream input = file.getInputStream()) {
            Files.copy(input, target);
        }
        return Map.of(
                "path", dataDirectory.relativize(target).toString(),
                "name", originalName,
                "media_type", file.getContentType() == null ? MediaType.APPLICATION_OCTET_STREAM_VALUE : file.getContentType(),
                "size", Files.size(target)
        );
    }

    @GetMapping("/content")
    public ResponseEntity<InputStreamResource> content(@RequestParam String path) throws IOException {
        Path file = resolve(path);
        String mediaType = Files.probeContentType(file);
        MediaType type = mediaType == null ? MediaType.APPLICATION_OCTET_STREAM : MediaType.parseMediaType(mediaType);
        InputStream input = Files.newInputStream(file);
        return ResponseEntity.ok()
                .contentType(type)
                .contentLength(Files.size(file))
                .header(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.inline().filename(file.getFileName().toString()).build().toString())
                .body(new InputStreamResource(input));
    }

    private Path resolve(String value) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException("path must not be blank");
        Path supplied = Path.of(value);
        Path file = (supplied.isAbsolute() ? supplied : dataDirectory.resolve(supplied)).toAbsolutePath().normalize();
        if (!file.startsWith(dataDirectory) || !Files.isRegularFile(file)) throw new IllegalArgumentException("file not found");
        return file;
    }
}
