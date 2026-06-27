import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// GitHub Pages 项目站点地址为 https://<user>.github.io/<repo>/，
// 构建产物需要以 /work/ 为根路径才能正确加载静态资源。
// 本地 dev 仍保持根路径 /，避免破坏 http://localhost:5173 的访问。
export default defineConfig(function (_a) {
    var command = _a.command;
    return ({
        plugins: [react()],
        base: command === "build" ? "/work/" : "/",
        server: {
            host: "0.0.0.0",
            port: 5173
        }
    });
});
