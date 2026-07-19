package com.github.erfanarvan.methodanalyzerapp;

public class Main {
    public static void main(String[] args) {
        try {
            String directoryPath = args.length > 0 ? args[0] : "repos";
            String manifestPath = args.length > 1 ? args[1] : "results/manifest.jsonl";

            System.out.println("Processing directory: " + directoryPath);
            System.out.println("Writing manifest to: " + manifestPath);
            DirectoryProcessor directoryProcessor = new DirectoryProcessor(directoryPath, manifestPath);
            directoryProcessor.processProjects();

            System.exit(0);
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(1);
        }
    }
}
