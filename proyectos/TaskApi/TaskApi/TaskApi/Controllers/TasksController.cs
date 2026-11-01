using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using TaskApi.Data;
using TaskApi.Models;

namespace TaskApi.Controllers;

[ApiController]
[Route("api/[controller]")]
public class TasksController : ControllerBase
{
    private readonly AppDbContext _context;

    public TasksController(AppDbContext context)
    {
        _context = context;
    }

    // GET: api/tasks            all tasks
    // GET: api/tasks?done=false only pending ones (done=true: only completed)
    [HttpGet]
    public async Task<ActionResult<IEnumerable<TaskItem>>> GetTasks(bool? done = null)
    {
        var query = _context.Tasks.AsNoTracking();
        if (done is not null)
            query = query.Where(t => t.IsCompleted == done);

        return await query.OrderBy(t => t.Id).ToListAsync();
    }

    // GET: api/tasks/5
    [HttpGet("{id:int}")]
    public async Task<ActionResult<TaskItem>> GetTask(int id)
    {
        var task = await _context.Tasks.FindAsync(id);
        return task is null ? NotFound() : task;
    }

    // POST: api/tasks   body: { "title": "Buy paper", "isCompleted": false }
    [HttpPost]
    public async Task<ActionResult<TaskItem>> CreateTask(TaskItem task)
    {
        task.Id = 0;                               // the database assigns the Id
        task.Title = task.Title.Trim();

        _context.Tasks.Add(task);
        await _context.SaveChangesAsync();

        return CreatedAtAction(nameof(GetTask), new { id = task.Id }, task);
    }

    // PUT: api/tasks/5   body: { "id": 5, "title": "...", "isCompleted": true }
    [HttpPut("{id:int}")]
    public async Task<IActionResult> UpdateTask(int id, TaskItem updated)
    {
        if (id != updated.Id)
            return BadRequest("The id in the address and in the body must match.");

        var task = await _context.Tasks.FindAsync(id);
        if (task is null)
            return NotFound();

        task.Title = updated.Title.Trim();
        task.IsCompleted = updated.IsCompleted;
        await _context.SaveChangesAsync();

        return NoContent();
    }

    // DELETE: api/tasks/5
    [HttpDelete("{id:int}")]
    public async Task<IActionResult> DeleteTask(int id)
    {
        var task = await _context.Tasks.FindAsync(id);
        if (task is null)
            return NotFound();

        _context.Tasks.Remove(task);
        await _context.SaveChangesAsync();

        return NoContent();
    }
}
