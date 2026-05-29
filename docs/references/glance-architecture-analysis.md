**总体结构**
`internal/glance` 是一个扁平的 Go 包，核心都是 `package glance`。入口在 [main.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/main.go:15)：`Main()` 解析 CLI，默认进入 `serveApp()`，读取配置、构建 `application`，并启动 HTTP 服务。运行时核心在 [glance.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/glance.go:30)，`application` 持有配置、页面索引、widget 索引、认证状态等。

目录组织大致是：

- `widget-*.go`：每个内置 widget 一个文件，例如 RSS、Reddit、Markets。
- [widget.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget.go:20)：widget 工厂、接口、基类、缓存调度。
- [config.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config.go:30)、[config-fields.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config-fields.go:25)：YAML 配置结构和自定义字段解析。
- [templates.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/templates.go:15)：模板函数和模板加载。
- [theme.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/theme.go:41)：主题属性、CSS 生成和主题切换。
- [auth.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/auth.go:23)：登录、session token、限流。
- `templates/`：服务端 HTML 模板。
- `static/`：CSS、JS、字体、图标、favicon。
- [embed.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/embed.go:20)：通过 `go:embed` 打包模板和静态资源。

**Widget 插件系统**
这里的“插件系统”是内置注册表模式，不是 Go 的动态 plugin。注册入口是 [widget.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget.go:20) 的 `newWidget(widgetType string)`，通过 `switch` 把 YAML 中的 `type` 映射到具体结构体，例如 `"rss"` 到 `&rssWidget{}`，`"reddit"` 到 `&redditWidget{}`，`"markets"`/`"stocks"` 到 `&marketsWidget{}`。

YAML 解码流程在 [widgets.UnmarshalYAML](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget.go:95)：先只解 `type`，调用 `newWidget()` 创建具体实例，再把同一个 YAML 节点 decode 到该实例。这让每个 widget 可以声明自己的 YAML 字段。

核心接口在 [widget.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget.go:126)：

```go
type widget interface {
    Render() template.HTML
    GetType() string
    GetID() uint64
    initialize() error
    requiresUpdate(*time.Time) bool
    setProviders(*widgetProviders)
    update(context.Context)
    ...
}
```

通用基类是 [widgetBase](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget.go:149)，保存 `Type`、`Title`、`TitleURL`、`HideHeader`、`CSSClass`、`cache`、运行时错误、notice、模板 buffer、下一次更新时间等。典型 widget 模式是：

```go
type rssWidget struct {
    widgetBase `yaml:",inline"`
    ...
}

func (widget *rssWidget) initialize() error { ... }
func (widget *rssWidget) update(ctx context.Context) { ... }
func (widget *rssWidget) Render() template.HTML { ... }
```

例如 RSS 在 [widget-rss.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-rss.go:31)，Reddit 在 [widget-reddit.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-reddit.go:21)，Markets 在 [widget-markets.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-markets.go:17)。

渲染路径是：`page.updateOutdatedWidgets()` 并发更新过期 widget [glance.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/glance.go:233)，`page-content.html` 遍历 `.Render` [page-content.html](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/templates/page-content.html:13)，每个 widget 再调用 `widgetBase.renderTemplate()` [widget.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget.go:217)。通用外壳由 [widget-base.html](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/templates/widget-base.html:1) 提供，具体模板只定义 `widget-content` block。

容器类 widget 复用 [containerWidgetBase](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-container.go:9)，例如 [groupWidget](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-group.go:12)、[splitColumnWidget](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-split-column.go:11)。静态 widget 可以在初始化时缓存 HTML，例如 bookmarks 在 [widget-bookmarks.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-bookmarks.go:70)。

**配置系统**
主配置结构在 [config.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config.go:30)，包括 `Server`、`Auth`、`Document`、`Theme`、`Branding`、`Pages`。页面结构在 [config.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config.go:77)，每页有 `HeadWidgets` 和 `Columns[].Widgets`。

加载流程在 [newConfigFromYAML](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config.go:94)：先 `parseConfigVariables()` 替换变量，再 `yaml.Unmarshal`，再 `isConfigStateValid()` 校验，最后遍历所有 widget 调 `initialize()`。

变量系统支持：

- `${API_KEY}`：环境变量。
- `${secret:api_key}`：读取 `/run/secrets/api_key`。
- `${readFileFromEnv:PATH}`：从环境变量指定的绝对路径读取文件。

实现见 [parseConfigVariables](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config.go:142) 和 [parseConfigVariableOfType](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config.go:190)。配置还支持 `!include:`/`$include:`，递归解析在 [recursiveParseYAMLIncludes](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config.go:246)，并用 fsnotify 做热重载 [configFilesWatcher](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config.go:305)。

`config-fields.go` 把 YAML 字段类型化：

- `hslColorField` 解析 HSL 并能转 hex [config-fields.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config-fields.go:25)。
- `durationField` 解析 `10s`、`5m`、`2h`、`1d` [config-fields.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config-fields.go:96)。
- `customIconField` 支持 `si:`、`di:`、`mdi:`、`sh:` 图标源和 `auto-invert` [config-fields.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config-fields.go:132)。
- `proxyOptionsField` 支持字符串或结构体形式，并构建带 proxy/TLS/timeout 的 `http.Client` [config-fields.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config-fields.go:190)。
- `queryParametersField` 把 string、number、bool、数组统一转为 query 参数 [config-fields.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/config-fields.go:237)。

**模板引擎**
模板基于 Go 标准库 `html/template`。全局函数在 [templates.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/templates.go:15)，包括 `formatApproxNumber`、`formatNumber`、`formatPrice`、`dynamicRelativeTimeAttrs`、`safeHTML`、`safeURL`、`safeCSS` 等。

模板加载模式是 [mustParseTemplate](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/templates.go:61)：

```go
template.New(primary).
    Funcs(globalTemplateFunctions).
    ParseFS(templateFS, append([]string{primary}, dependencies...)...)
```

所以每个 widget 通常声明一个包级模板变量，例如 [rssWidgetTemplate](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-rss.go:23) 使用 `mustParseTemplate("rss-list.html", "widget-base.html")`。页面外壳由 [document.html](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/templates/document.html:1) 和 [page.html](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/templates/page.html:1) 组成，具体页面内容由 [page-content.html](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/templates/page-content.html:13) 异步填充。

**主题系统**
主题配置结构是 [themeProperties](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/theme.go:41)，字段包括背景色、主色、正负色、亮色模式、对比度倍率、文字饱和度倍率。`init()` 会把主题编译成 CSS 和预览 HTML [theme.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/theme.go:56)。CSS 模板是 [theme-style.gotmpl](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/templates/theme-style.gotmpl:1)，本质是写入 `:root` CSS 变量。

`newApplication()` 会注入默认 dark/light 主题，并把用户 presets 合并进有序 map [glance.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/glance.go:104)。请求时 [populateTemplateRequestData](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/glance.go:290) 根据 `theme` cookie 选择主题。切换主题走 `POST /api/set-theme/{key}`，处理函数在 [theme.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/theme.go:15)：设置 cookie，返回新 CSS，并用 `X-Scheme` 告诉前端 light/dark。

**认证体系**
认证是配置驱动的：只要 `auth.users` 非空，`newApplication()` 就启用认证 [glance.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/glance.go:61)。`secret-key` 是 base64 后的 64 字节，前 32 字节用于 token HMAC，后 32 字节用于 username hash HMAC。用户密码可以是明文配置后启动时 bcrypt，也可以是 `password-hash` [glance.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/glance.go:83)。

session token 生成在 [generateSessionToken](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/auth.go:52)：内容是 username hash、过期时间、HMAC 签名，再 base64。验证在 [verifySessionToken](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/auth.go:88)，有效期 14 天，剩余少于 7 天会重新签发。

登录接口 [handleAuthenticationAttempt](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/auth.go:134) 要求 JSON，按 IP 做 5 分钟 5 次失败限制，失败有延迟。成功后设置 `session_token` cookie，`HttpOnly`、`SameSite=Lax`，如果 `X-Forwarded-Proto=https` 则 `Secure` [auth.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/auth.go:311)。页面请求未授权会跳 `/login`，API 内容请求返回 JSON 401 [auth.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/auth.go:288)。

**数据源 Widget 抓取模式**
通用 HTTP/并发工具在 [widget-utils.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-utils.go:19)：默认 client 5 秒超时，JSON/XML 泛型解码，浏览器 UA，`workerPoolDo` 泛型 worker pool。错误分为 `errNoContent` 和 `errPartialContent`，由 [canContinueUpdateAfterHandlingErr](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget.go:293) 统一转成错误、notice 和提前重试。

RSS： [widget-rss.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-rss.go:31) 使用 `gofeed`，每个 feed 并发抓取，worker 数 30 [widget-rss.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-rss.go:152)。支持 ETag/Last-Modified 条件请求和内存缓存 [widget-rss.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-rss.go:200)，去重按 link，默认按发布时间排序，支持 list/detailed/horizontal cards 多模板。

Hacker News： [widget-hacker-news.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-hacker-news.go:14) 先请求 Firebase API 的 `{sort}stories.json` [widget-hacker-news.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-hacker-news.go:78)，再并发请求每个 item [widget-hacker-news.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-hacker-news.go:88)，映射为通用 `forumPost`，复用 [forum-posts.html](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/templates/forum-posts.html:1)。

Reddit： [widget-reddit.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-reddit.go:21) 支持匿名 `www.reddit.com` JSON，也支持 app-auth OAuth `oauth.reddit.com` [widget-reddit.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-reddit.go:160)。支持 proxy、`request-url-template`、搜索、hot/new/top/rising、top period、flair、thumbnail、crosspost。OAuth token 用 client credentials 获取并缓存到过期时间 [widget-reddit.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-reddit.go:283)。

Markets： [widget-markets.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-markets.go:17) 访问 Yahoo Finance chart API [widget-markets.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/widget-markets.go:124)，并发解码每个 symbol，取最近约 21 天 close 生成 SVG 折线点，计算百分比涨跌，映射货币符号，支持按涨跌排序。

**静态资源和前端**
静态资源和模板都通过 `go:embed` 打入二进制 [embed.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/embed.go:20)。静态文件内容会计算 MD5 短 hash，URL 形如 `/static/{hash}/...` [embed.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/embed.go:42)，HTTP 层设置 24 小时缓存 [glance.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/glance.go:459)。

CSS 入口是 [main.css](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/static/css/main.css:60)，导入 `site.css`、`widgets.css`、`popover.css`、`utils.css`、`mobile.css`。`widgets.css` 再导入各 widget 样式 [widgets.css](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/static/css/widgets.css:1)。[embed.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/embed.go:87) 在运行时递归展开 `@import`，生成 `css/bundle.css`。

前端不是 SPA 框架，而是服务端模板加少量 ES module 增强。`page.html` 初始只放 `#page-content` 和 loading [page.html](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/templates/page.html:106)，[page.js](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/static/js/page.js:6) 再请求 `/api/pages/{slug}/content/`，插入 HTML 后初始化 popover、masonry、carousel、搜索框、折叠列表、相对时间、clock、calendar、todo 等 [page.js](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/static/js/page.js:746)。用户自定义资源通过 `server.assets-path` 暴露到 `/assets/` [glance.go](/home/suuuu/develop/intelligence-system/archive/glance/internal/glance/glance.go:484)。