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
