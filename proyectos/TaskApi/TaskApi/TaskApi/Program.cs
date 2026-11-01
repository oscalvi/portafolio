using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

var builder = WebApplication.CreateBuilder(args);

// ------------------------------------------------------------
// Services
// ------------------------------------------------------------
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

// ------------------------------------------------------------
// Middleware
// ------------------------------------------------------------
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();

// ------------------------------------------------------------
// Root endpoint
// ------------------------------------------------------------
app.MapGet("/", () => "TaskApi is running");

// ------------------------------------------------------------
// Health check
// ------------------------------------------------------------
app.MapGet("/health", () =>
{
    return Results.Json(new
    {
        status = "healthy",
        time = DateTime.UtcNow
    });
});

// ------------------------------------------------------------
// Version endpoint
// ------------------------------------------------------------
app.MapGet("/version", () =>
{
    return Results.Json(new
    {
        api = "TaskApi",
        version = "v1.0.0",
        framework = "net10.0"
    });
});

// ------------------------------------------------------------
// Endpoint list (no inferred parameters)
// ------------------------------------------------------------
app.MapGet("/endpoints", () =>
{
    var dataSource = app.Services.GetRequiredService<EndpointDataSource>();

    var endpoints = dataSource.Endpoints
        .OfType<RouteEndpoint>()
        .Select(e => e.RoutePattern.RawText)
        .ToList();

    return Results.Json(endpoints);
});

// ------------------------------------------------------------
// Your existing API routes (Tasks, etc.)
// ------------------------------------------------------------
// Mantén tus rutas actuales aquí.
// Ejemplo:
// app.MapGet("/api/Tasks", () => ...);
// app.MapPost("/api/Tasks", (TaskModel model) => ...);

// ------------------------------------------------------------
// Run
// ------------------------------------------------------------
app.Run();
