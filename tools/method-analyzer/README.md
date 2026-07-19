# MethodAnalyzerApp

Method Analyzer App is a Java tool that analyzes Java source code files to extract detailed information about methods. It uses **JavaParser** to parse Java files and outputs method details into CSV files for easy inspection.

## Features  
The tool extracts the following details for each method:  
- **Method Name, Class, Package**  
- **Return Type, Parameters, Access Modifiers**  
- **Annotations and Javadoc Comments**  
- **Expressions and Their Resolved Types**  
- **Number of Lines of Code (Raw & Cleaned)**  

## Installation  

### **Clone the Repository**  
```sh
git clone https://github.com/yourusername/MethodAnalyzerApp.git
cd MethodAnalyzerApp
```

### **Build the Project**  
Ensure you have **JDK 17+** installed. Then, build the project:
```sh
# For Linux/macOS
./gradlew build

# For Windows
gradlew build
```

## Usage  

1. **Place the target Java project directories** inside the `./repos` directory.  
2. **Run the program** using Gradle Wrapper:
   ```sh
   # For Linux/macOS
   ./gradlew run

   # For Windows
   gradlew run
   ```
3. **Find the results** in the `./results` directory:
   - Each analyzed project `p` will have a corresponding CSV file:  
     ```
     ./results/p_methods.csv
     ```
   - There is also an **aggregated** file named:  
     ```
     ./results/aggregated_methods.csv
     ```
     which contains method details from **all** analyzed projects.

---
Happy Coding! 🚀
Erfan
