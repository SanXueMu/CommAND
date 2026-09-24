package com.zthcpa.command.tools;

import java.util.List;

public interface TranslationModel {
    TranslationBatch translate(List<String> segments, TranslationOptions options, ProgressSink progress);
}
