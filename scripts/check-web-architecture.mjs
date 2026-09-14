import { readFileSync, readdirSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import ts from "typescript";

const root = resolve("web");
const errors = [];
function walk(folder) {
  return readdirSync(folder, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(folder, entry.name);
    return entry.isDirectory() ? walk(path) : /\.[cm]?tsx?$/.test(path) ? [path] : [];
  });
}
for (const path of walk(root)) {
  const file = relative(root, path).replaceAll("\\", "/");
  const source = ts.createSourceFile(path, readFileSync(path, "utf8"), ts.ScriptTarget.Latest, true);
  function inspect(node) {
    const line = source.getLineAndCharacterOfPosition(node.getStart()).line + 1;
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      const value = node.moduleSpecifier.text;
      const target = value.startsWith(".") ? resolve(dirname(path), value).replaceAll("\\", "/") : value;
      if (target.includes("/backend/") || value.startsWith("backend/")) {
        errors.push(`${file}:${line} 前端不能导入后端实现`);
      }
      if (
        (target.includes("/app/page") ||
          target.includes("/app/demo/") ||
          target.endsWith("/app/globals.css")) &&
        file !== "app/DemoPage.tsx"
      ) {
        errors.push(`${file}:${line} 演示依赖只能由隔离的DemoPage加载`);
      }
      if (file.startsWith("shared/") && target.includes("/web/modules/")) {
        errors.push(`${file}:${line} 公共组件不能反向依赖业务模块`);
      }
      if (file.startsWith("modules/")) {
        const targetModule = target.match(/\/web\/modules\/([^/]+)\/(.+)/);
        if (targetModule && targetModule[1] !== file.split("/")[1] && targetModule[2] !== "api") {
          errors.push(`${file}:${line} 跨模块仅允许使用公开API契约`);
        }
      }
    }
    if (
      ts.isCallExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === "fetch" &&
      file !== "shared/api/http.ts"
    ) {
      errors.push(`${file}:${line} fetch必须集中在shared/api/http.ts`);
    }
    ts.forEachChild(node, inspect);
  }
  inspect(source);
}
if (errors.length) {
  console.error(errors.join("\n"));
  process.exitCode = 1;
} else {
  console.log("前端模块依赖与请求边界检查通过");
}
