package com.conkord.genai;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/** Incorpora los informes existentes al respaldo sin modificar sus bytes. */
@Component
public class HistoryBackupInitializer implements ApplicationRunner {
    private final PatientHistoryService histories;
    public HistoryBackupInitializer(PatientHistoryService histories) { this.histories = histories; }
    @Override
    public void run(ApplicationArguments args) { histories.backupExisting(); }
}
