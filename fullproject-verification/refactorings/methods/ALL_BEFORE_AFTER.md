# Refactored methods: before / after

Original code is at the pinned commit of each repo; "after" is the same method with `../patches/<case>_*.patch` applied.

## row13: org.apache.dubbo.common.utils.ReflectUtils.getGenericClass

dubbo, index checker, warning `array.access.unsafe.high.constant,array.access.unsafe.low,array.access.unsafe.high`  
File: `dubbo-common/src/main/java/org/apache/dubbo/common/utils/ReflectUtils.java`

### Before
```java
    public static Class<?> getGenericClass(Class<?> cls, int i) {
        try {
            ParameterizedType parameterizedType = ((ParameterizedType) cls.getGenericInterfaces()[0]);
            Object genericClass = parameterizedType.getActualTypeArguments()[i];

            // handle nested generic type
            if (genericClass instanceof ParameterizedType) {
                return (Class<?>) ((ParameterizedType) genericClass).getRawType();
            }

            // handle array generic type
            if (genericClass instanceof GenericArrayType) {
                return (Class<?>) ((GenericArrayType) genericClass).getGenericComponentType();
            }

            // Requires JDK 7 or higher, Foo<int[]> is no longer GenericArrayType
            if (((Class) genericClass).isArray()) {
                return ((Class) genericClass).getComponentType();
            }
            return (Class<?>) genericClass;
        } catch (Throwable e) {
            throw new IllegalArgumentException(cls.getName() + " generic type undefined!", e);
        }
    }
```

### After
```java
    public static Class<?> getGenericClass(Class<?> cls, int i) {
        Type[] genericInterfaces = cls.getGenericInterfaces();
        if (genericInterfaces.length == 0 || !(genericInterfaces[0] instanceof ParameterizedType)) {
            throw new IllegalArgumentException(cls.getName() + " generic type undefined!");
        }
        Type[] typeArguments = ((ParameterizedType) genericInterfaces[0]).getActualTypeArguments();
        if (i < 0 || i >= typeArguments.length) {
            throw new IllegalArgumentException(cls.getName() + " generic type undefined!");
        }
        Object genericClass = typeArguments[i];
        try {
            // handle nested generic type
            if (genericClass instanceof ParameterizedType) {
                return (Class<?>) ((ParameterizedType) genericClass).getRawType();
            }

            // handle array generic type
            if (genericClass instanceof GenericArrayType) {
                return (Class<?>) ((GenericArrayType) genericClass).getGenericComponentType();
            }

            // Requires JDK 7 or higher, Foo<int[]> is no longer GenericArrayType
            if (((Class) genericClass).isArray()) {
                return ((Class) genericClass).getComponentType();
            }
            return (Class<?>) genericClass;
        } catch (Throwable e) {
            throw new IllegalArgumentException(cls.getName() + " generic type undefined!", e);
        }
    }
```

## row16: org.apache.dubbo.common.utils.UrlUtils.isMatchGlobPattern

dubbo, index checker, warning `argument`  
File: `dubbo-common/src/main/java/org/apache/dubbo/common/utils/UrlUtils.java`

### Before
```java
    public static boolean isMatchGlobPattern(String pattern, String value) {
        if ("*".equals(pattern)) {
            return true;
        }
        if (StringUtils.isEmpty(pattern) && StringUtils.isEmpty(value)) {
            return true;
        }
        if (StringUtils.isEmpty(pattern) || StringUtils.isEmpty(value)) {
            return false;
        }

        int i = pattern.lastIndexOf('*');
        // doesn't find "*"
        if (i == -1) {
            return value.equals(pattern);
        }
        // "*" is at the end
        else if (i == pattern.length() - 1) {
            return value.startsWith(pattern.substring(0, i));
        }
        // "*" is at the beginning
        else if (i == 0) {
            return value.endsWith(pattern.substring(i + 1));
        }
        // "*" is in the middle
        else {
            String prefix = pattern.substring(0, i);
            String suffix = pattern.substring(i + 1);
            return value.startsWith(prefix) && value.endsWith(suffix);
        }
    }
```

### After
```java
    public static boolean isMatchGlobPattern(String pattern, String value) {
        if ("*".equals(pattern)) {
            return true;
        }
        if (pattern == null || pattern.isEmpty()) {
            return value == null || value.isEmpty();
        }
        if (value == null || value.isEmpty()) {
            return false;
        }

        int i = pattern.lastIndexOf('*');
        // doesn't find "*"
        if (i == -1) {
            return value.equals(pattern);
        }
        // "*" is at the end
        else if (i == pattern.length() - 1) {
            return value.startsWith(pattern.substring(0, i));
        }
        // "*" is at the beginning
        else if (i == 0) {
            return value.endsWith(pattern.substring(i + 1));
        }
        // "*" is in the middle
        else {
            String prefix = pattern.substring(0, i);
            String suffix = pattern.substring(i + 1);
            return value.startsWith(prefix) && value.endsWith(suffix);
        }
    }
```

## row54: ghidra.app.util.bin.format.macho.MachHeaderFlags.getFlags

ghidra, index checker, warning `argument`  
File: `Ghidra/Features/Base/src/main/java/ghidra/app/util/bin/format/macho/MachHeaderFlags.java`

### Before
```java
	public final static List<String> getFlags(int flags) {
		List<String> list = new ArrayList<>();
		Field[] fields = MachHeaderFlags.class.getDeclaredFields();
		for (Field field : fields) {
			if (field.getName().startsWith("MH_")) {
				try {
					Integer value = (Integer) field.get(null);
					if ((flags & value) != 0) {
						list.add(field.getName().substring("MH_".length()));
					}
				}
				catch (Exception e) {
					// do nothing
				}
			}
		}
		return list;
	}
```

### After
```java
	public final static List<String> getFlags(int flags) {
		List<String> list = new ArrayList<>();
		Field[] fields = MachHeaderFlags.class.getDeclaredFields();
		for (Field field : fields) {
			String name = field.getName();
			if (name.startsWith("MH_")) {
				try {
					Integer value = (Integer) field.get(null);
					if ((flags & value) != 0) {
						list.add(name.substring("MH_".length()));
					}
				}
				catch (Exception e) {
					// do nothing
				}
			}
		}
		return list;
	}
```

## row90: ghidra.program.util.InstructionUtils.getFormatedInstructionObjects

ghidra, nullness checker, warning `toarray.nullable.elements.not.newarray`  
File: `Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/util/InstructionUtils.java`

### Before
```java
	private static String[] getFormatedInstructionObjects(Object[] objs) {
		if (objs == null) {
			return null;
		}
		HashSet<String> set = new HashSet<String>();
		for (Object element : objs) {
			if (element instanceof Scalar) {
				Scalar scalar = (Scalar) element;
				set.add("const:" + scalar.toString());
			}
			else if (element instanceof Register) {
				Register reg = (Register) element;
				set.add(reg.toString());
			}
			else if (element instanceof Address) {
				Address addr = (Address) element;
				set.add(addr.toString(true));
			}
		}
		String[] list = new String[set.size()];
		set.toArray(list);
		Arrays.sort(list, OBJSTRING_COMPARATOR);
		return list;
	}
```

### After
```java
	private static String[] getFormatedInstructionObjects(Object[] objs) {
		if (objs == null) {
			return null;
		}
		HashSet<String> set = new HashSet<String>();
		for (Object element : objs) {
			if (element instanceof Scalar) {
				Scalar scalar = (Scalar) element;
				set.add("const:" + scalar.toString());
			}
			else if (element instanceof Register) {
				Register reg = (Register) element;
				set.add(reg.toString());
			}
			else if (element instanceof Address) {
				Address addr = (Address) element;
				set.add(addr.toString(true));
			}
		}
		String[] list = set.toArray(new String[set.size()]);
		Arrays.sort(list, OBJSTRING_COMPARATOR);
		return list;
	}
```

## row114: org.apache.hudi.common.table.view.HoodieTableFileSystemView.fetchAllStoredFileGroups

hudi, nullness checker, warning `argument`  
File: `hudi-common/src/main/java/org/apache/hudi/common/table/view/HoodieTableFileSystemView.java`

### Before
```java
  @Override
  Stream<HoodieFileGroup> fetchAllStoredFileGroups(String partition) {
    List<HoodieFileGroup> fileGroups = partitionToFileGroupsMap.get(partition);
    if (fileGroups == null || fileGroups.isEmpty()) {
      LOG.warn("Partition: {} is not available in store", partition);
      return Stream.empty();
    }
    return new ArrayList<>(partitionToFileGroupsMap.get(partition)).stream();
  }
```

### After
```java
  @Override
  Stream<HoodieFileGroup> fetchAllStoredFileGroups(String partition) {
    List<HoodieFileGroup> fileGroups = partitionToFileGroupsMap.get(partition);
    if (fileGroups == null || fileGroups.isEmpty()) {
      LOG.warn("Partition: {} is not available in store", partition);
      return Stream.empty();
    }
    return new ArrayList<>(fileGroups).stream();
  }
```

## row94: ghidra.util.database.spatial.hyper.EuclideanHyperSpace.collectBounds

ghidra, index checker, warning `array.access.unsafe.high`  
File: `Ghidra/Debug/ProposedUtils/src/main/java/ghidra/util/database/spatial/hyper/EuclideanHyperSpace.java`

### Before
```java
	default Object[] collectBounds(B box) {
		List<Dimension<?, P, B>> dims = getDimensions();
		Object[] result = new Object[dims.size() * 2];
		for (int i = 0; i < dims.size(); i++) {
			Dimension<?, P, B> d = dims.get(i);
			result[i * 2] = d.lower(box);
			result[i * 2 + 1] = d.upper(box);
		}
		return result;
	}
```

### After
```java
	default Object[] collectBounds(B box) {
		List<Dimension<?, P, B>> dims = getDimensions();
		Object[] result = new Object[dims.size() * 2];
		Iterator<Dimension<?, P, B>> it = dims.iterator();
		for (int j = 0; j + 1 < result.length; j += 2) {
			Dimension<?, P, B> d = it.next();
			result[j] = d.lower(box);
			result[j + 1] = d.upper(box);
		}
		return result;
	}
```

