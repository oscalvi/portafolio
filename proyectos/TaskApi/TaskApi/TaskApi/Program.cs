using Microsoft.AspNetCore.Routing;
using Microsoft.EntityFrameworkCore;
using TaskApi.Data;

var builder = WebApplication.CreateBuilder(args);

// ------------------------------------------------------------
// Services
// ------------------------------------------------------------
builder.Services.AddControllers();                 // turns on TasksController (api/tasks)
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// Database: SQLite file next to the app (taskapi.db). The connection string
// lives in appsettings.json ("TaskDb"); change it there, not in the code.
var connection = builder.Configuration.GetConnectionString("TaskDb")
                 ?? "Data Source=taskapi.db";
builder.Services.AddDbContext<AppDbContext>(options => options.UseSqlite(connection));

var app = builder.Build();

// Create the database and the Tasks table the first time the API starts.
using (var scope = app.Services.CreateScope())
{
    scope.ServiceProvider.GetRequiredService<AppDbContext>().Database.EnsureCreated();
}

// ------------------------------------------------------------
// Middleware
// ------------------------------------------------------------
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();                            // http://localhost:5079/swagger
}

// ------------------------------------------------------------
// Root, health and version
// ------------------------------------------------------------
app.MapGet("/", () => "TaskApi is running. Open /swagger to try it.");

app.MapGet("/health", () => Results.Json(new
{
    status = "healthy",
    time = DateTime.UtcNow
}));

app.MapGet("/version", () => Results.Json(new
{
    api = "TaskApi",
    version = "v1.1.0",
    framework = "net10.0"
}));

// Endpoint list
app.MapGet("/endpoints", (EndpointDataSource dataSource) => Results.Json(
    dataSource.Endpoints
        .OfType<RouteEndpoint>()
        .Select(e => e.RoutePattern.RawText)
        .ToList()));

// ------------------------------------------------------------
// Tasks: GET/POST /api/tasks, GET/PUT/DELETE /api/tasks/{id}
// ------------------------------------------------------------
app.MapControllers();

app.Run();
