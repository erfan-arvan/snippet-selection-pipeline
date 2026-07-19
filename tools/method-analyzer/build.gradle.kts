plugins {
    id("java")
    id ("application")
    id("com.gradleup.shadow") version "8.3.5"
}

group = "com.github.erfanarvan.methodanalyzerapp"
version = "1.0-SNAPSHOT"

repositories {
    mavenCentral()
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.9.1"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    implementation("com.github.javaparser:javaparser-core:3.25.2")
    implementation("com.github.javaparser:javaparser-symbol-solver-core:3.25.2")
    implementation("com.google.guava:guava:31.1-jre")
    implementation ("com.google.googlejavaformat:google-java-format:1.17.0")
    implementation ("org.apache.commons:commons-lang3:3.12.0")
    implementation("com.google.code.gson:gson:2.10.1")
    testImplementation("org.junit.jupiter:junit-jupiter:5.9.2")
}
application {
    mainClass.set("com.github.erfanarvan.methodanalyzerapp.Main")
}

tasks.test {
    useJUnitPlatform()
}

// The orchestrator invokes both Main (batch filtering) and LocateMethod (post-slice
// re-location) as plain `java -jar` calls, potentially thousands of times per pipeline run.
// A shadow/fat jar avoids paying Gradle daemon + classpath-assembly overhead on every call.
tasks.shadowJar {
    archiveBaseName.set("method-analyzer-all")
    archiveClassifier.set("")
    archiveVersion.set("")
    mergeServiceFiles()
}

sourceSets {
    test {
        java {
            setSrcDirs(listOf("src/test/java"))
        }
    }
}
