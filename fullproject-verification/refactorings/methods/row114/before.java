  @Override
  Stream<HoodieFileGroup> fetchAllStoredFileGroups(String partition) {
    List<HoodieFileGroup> fileGroups = partitionToFileGroupsMap.get(partition);
    if (fileGroups == null || fileGroups.isEmpty()) {
      LOG.warn("Partition: {} is not available in store", partition);
      return Stream.empty();
    }
    return new ArrayList<>(partitionToFileGroupsMap.get(partition)).stream();
  }
