/** 只读取文件字节；格式和业务校验由后端负责。 */
export function readImportFile(file: File): Promise<{ filename: string; content: string }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("文件读取失败，请重新选择"));
    reader.onload = () => {
      if (typeof reader.result !== "string") return reject(new Error("文件读取失败"));
      resolve({ filename: file.name, content: reader.result.slice(reader.result.indexOf(",") + 1) });
    };
    reader.readAsDataURL(file);
  });
}
